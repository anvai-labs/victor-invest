"""
SEC Filing Analysis Agent
Specialized agent for processing and analyzing SEC filings using Ollama LLMs
"""

import asyncio
import gzip
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from investigator.config import get_config
from investigator.domain.agents.base import InvestmentAgent
from investigator.domain.models.analysis import AgentResult, AgentTask, TaskStatus
from investigator.domain.services.filing_guidance_extractor import (
    extract_forward_guidance,
    select_best_guidance,
)
from investigator.infrastructure.cache import CacheManager
from investigator.infrastructure.database.market_data import (  # Singleton pattern
    get_market_data_fetcher,
)

# Use direct module imports to avoid circular dependency with sec package __init__.py
from investigator.infrastructure.sec.sec_api import SECApiClient
from investigator.infrastructure.sec.xbrl_parser import XBRLParser

logger = logging.getLogger(__name__)


@dataclass
class SECFilingData:
    """Structured SEC filing data"""

    cik: str
    symbol: str
    filing_type: str
    filing_date: datetime
    period_end: datetime
    form_url: str
    xbrl_url: str | None
    raw_text: str
    extracted_sections: dict[str, str]
    financial_data: dict[str, Any]


class SECAnalysisAgent(InvestmentAgent):
    """
    Agent specialized in SEC filing analysis and financial data extraction
    """

    def __init__(self, agent_id: str, ollama_client, event_bus, cache_manager: CacheManager):
        config = get_config()
        self.primary_model = config.ollama.models.get("fundamental_analysis", "deepseek-r1:32b")
        self.summary_model = config.ollama.models.get("synthesis", self.primary_model)

        # Specialized models for different tasks (set before base __init__ so capabilities use them)
        self.models = {
            "extraction": self.primary_model,
            "analysis": self.primary_model,
            "summary": self.summary_model,
        }

        super().__init__(agent_id, ollama_client, event_bus, cache_manager)
        self.sec_client = SECApiClient()
        self.xbrl_parser = XBRLParser()
        self.market_data = get_market_data_fetcher(config)

        # Section patterns for 10-K/10-Q forms
        self.section_patterns = {
            "business": r"Item\s+1[.\s]+Business",
            "risk_factors": r"Item\s+1A[.\s]+Risk\s+Factors",
            "properties": r"Item\s+2[.\s]+Properties",
            "legal": r"Item\s+3[.\s]+Legal\s+Proceedings",
            "mda": r"Item\s+7[.\s]+Management.*Discussion.*Analysis",
            "financial_statements": r"Item\s+8[.\s]+Financial\s+Statements",
            "controls": r"Item\s+9A[.\s]+Controls.*Procedures",
        }

    def register_capabilities(self) -> list:
        """Register agent capabilities"""
        from investigator.domain.agents.base import AgentCapability, AnalysisType

        return [
            AgentCapability(
                analysis_type=AnalysisType.SEC_FUNDAMENTAL,
                min_data_required={"symbol": str, "filing_type": str},
                max_processing_time=600,  # Increased 2x for slower hardware
                required_models=[self.primary_model],
                cache_ttl=3600,
            )
        ]

    async def pre_process(self, task: AgentTask) -> str | None:
        """
        Validate database consistency before accepting file cache.

        CRITICAL FIX: File cache may exist but database tables may be empty (cache inconsistency).
        This happens when a previous run failed partway through, leaving file cache markers
        but empty database tables.

        Returns:
            None if validation passes, error message if validation fails
        """
        symbol = task.context.get("symbol")

        # Check if processed data exists in database
        from sqlalchemy import text

        from investigator.infrastructure.database.db import get_db_manager

        db_manager = get_db_manager()
        with db_manager.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM sec_companyfacts_processed
                    WHERE symbol = :symbol
                """),
                {"symbol": symbol},
            ).fetchone()

            if result.count == 0:
                # Database is empty - clear file cache to force refetch
                self.logger.warning(
                    f"[SEC Agent] Cache inconsistency detected for {symbol}: "
                    f"file cache exists but database has 0 rows. Clearing file cache."
                )

                # Clear file cache for this symbol

                {
                    "symbol": symbol,
                    "analysis_type": "sec_fundamental",
                    "context_hash": task.get_cache_key()[:8],
                }

                # Clear the cache entry to force refetch
                try:
                    # Delete file cache entries for this symbol
                    import shutil
                    from pathlib import Path

                    cache_dir = Path("data/sec_cache") / symbol
                    if cache_dir.exists():
                        self.logger.info(f"[SEC Agent] Removing cache directory: {cache_dir}")
                        shutil.rmtree(cache_dir)
                except Exception as e:
                    self.logger.error(f"[SEC Agent] Failed to clear cache for {symbol}: {e}")

        return await super().pre_process(task)

    async def process(self, task: AgentTask) -> AgentResult:
        """
        Process SEC data fetching task.

        PRIMARY RESPONSIBILITY: Fetch and cache raw SEC CompanyFacts data for downstream agents.
        This is the ONLY agent that calls the SEC CompanyFacts API.
        All other agents (Fundamental, Technical, etc.) read from this cache.
        """
        symbol = task.context.get("symbol")
        filing_type = task.context.get("filing_type", "10-K")
        period = task.context.get("period", "latest")
        force_refresh = self._resolve_force_refresh(symbol, task)

        self.logger.info(f"[SEC Agent] Fetching raw CompanyFacts data for {symbol}")

        try:
            # PRIMARY TASK: Fetch and cache RAW SEC CompanyFacts data
            raw_companyfacts = await self._fetch_and_cache_companyfacts(symbol, force_refresh=force_refresh)

            # SECONDARY TASK: Analyze filing sections (MD&A, Risk Factors, etc.)
            # This is optional and can be skipped for faster execution
            filing_analysis = {}
            if task.context.get("analyze_filings", False):
                self.logger.info(f"[SEC Agent] Analyzing filing sections for {symbol}")
                filing_data = await self._fetch_filing(symbol, filing_type, period)
                sections = await self._extract_sections(filing_data)

                # Analyze risk factors
                risks = await self._analyze_risks(sections.get("risk_factors", ""), symbol)

                # Analyze MD&A
                mda_analysis = await self._analyze_mda(sections.get("mda", ""), symbol)

                filing_analysis = {
                    "risks": risks,
                    "mda_analysis": mda_analysis,
                    "filing_url": filing_data.form_url,
                    "filing_date": filing_data.filing_date.isoformat(),
                }

            # Forward guidance extraction for forward valuation basis.
            forward_guidance = {}
            if self._should_extract_forward_guidance(task):
                forward_guidance = await self._extract_forward_guidance(
                    symbol,
                    force_refresh=force_refresh,
                )
                if forward_guidance:
                    self.logger.info(
                        "[SEC Agent] Extracted forward guidance for %s from %s (confidence=%.2f, rev_range=%s, eps_range=%s, rev_growth=%s, earn_growth=%s)",
                        symbol,
                        forward_guidance.get("source_form", "unknown"),
                        float(forward_guidance.get("confidence_score", 0.0) or 0.0),
                        bool(forward_guidance.get("revenue_guidance")),
                        bool(forward_guidance.get("eps_guidance")),
                        forward_guidance.get("revenue_growth_guidance"),
                        forward_guidance.get("earnings_growth_guidance"),
                    )
                else:
                    self.logger.info(
                        "[SEC Agent] No deterministic forward guidance found for %s",
                        symbol,
                    )

            # Extract summary info from raw_companyfacts instead of including all 4MB of data
            companyfacts_summary = {}
            if raw_companyfacts and "facts" in raw_companyfacts:
                processed_dir = Path("data/sec_cache/facts/processed") / symbol.upper()
                raw_dir = Path("data/sec_cache/facts/raw") / symbol.upper()
                companyfacts_summary = {
                    "cik": raw_companyfacts.get("cik"),
                    "entityName": raw_companyfacts.get("entityName"),
                    "fact_count": sum(
                        len(concepts)
                        for taxonomy in raw_companyfacts["facts"].values()
                        for concepts in taxonomy.values()
                    ),
                    "taxonomies": list(raw_companyfacts["facts"].keys()),
                    "data_cached": True,
                    "cache_location": str(processed_dir),
                    "processed_cache_location": str(processed_dir),
                    "raw_cache_location": str(raw_dir),
                }

            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.COMPLETED,
                result_data={
                    "status": "success",
                    "symbol": symbol,
                    "companyfacts_summary": companyfacts_summary,  # Summary instead of full 4MB data
                    "filing_analysis": filing_analysis,  # Optional LLM analysis
                    "forward_guidance": forward_guidance,
                    "data_cached": True,  # Indicates data is in cache
                },
                processing_time=0,  # Will be calculated by base class
            )

        except Exception as e:
            self.logger.error(f"[SEC Agent] Failed for {symbol}: {e}")
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                result_data={"status": "error", "symbol": symbol, "error": str(e)},
                processing_time=0,
                error=str(e),
            )

    def _should_extract_forward_guidance(self, task: AgentTask) -> bool:
        """Return True when the downstream valuation path requests forward denominators."""
        valuation_basis = str(task.context.get("valuation_basis", "ttm")).strip().lower()
        if valuation_basis == "forward":
            return True
        return bool(task.context.get("extract_guidance", False))

    async def _extract_forward_guidance(self, symbol: str, *, force_refresh: bool = False) -> dict[str, Any]:
        """
        Fetch latest filings and deterministically extract guidance signals.

        Uses SEC_RESPONSE cache to avoid repeated text fetch/parsing per symbol.
        Extraction order:
        1) Deterministic regex extractor (cheap/stable)
        2) LLM JSON fallback when deterministic extractor misses or yields weak partial output
        """
        from investigator.infrastructure.cache.cache_types import CacheType

        cache_key = {
            "symbol": symbol,
            "category": "forward_guidance",
            "version": "v4",
        }
        if not force_refresh:
            cached = self.cache.get(CacheType.SEC_RESPONSE, cache_key) if self.cache else None
            if isinstance(cached, dict) and cached:
                return cached

        candidates: list[dict[str, Any]] = []
        for form_type in ("8-K", "10-Q", "10-K"):
            try:
                filing = await self.sec_client.get_filing_by_symbol(
                    symbol=symbol,
                    form_type=form_type,
                    period="latest",
                )
            except Exception as exc:
                self.logger.debug(
                    "[SEC Agent] Guidance fetch skipped for %s %s: %s",
                    symbol,
                    form_type,
                    exc,
                )
                continue

            text = filing.get("text") or ""
            if not text:
                continue

            extracted = extract_forward_guidance(
                text=text[:250_000],
                form_type=form_type,
                filing_date=filing.get("filing_date"),
            )
            regex_extracted = extracted if isinstance(extracted, dict) else {}
            llm_needed = self._is_weak_guidance_payload(regex_extracted)
            if llm_needed:
                llm_extracted = await self._extract_forward_guidance_with_llm(
                    symbol=symbol,
                    form_type=form_type,
                    filing_date=filing.get("filing_date"),
                    filing_url=filing.get("form_url"),
                    filing_text=text,
                )
                if llm_extracted and regex_extracted:
                    extracted = select_best_guidance([regex_extracted, llm_extracted])
                elif llm_extracted:
                    extracted = llm_extracted
                else:
                    extracted = regex_extracted
            if not extracted:
                continue

            extracted["symbol"] = symbol
            extracted["filing_url"] = filing.get("form_url")
            candidates.append(extracted)
            confidence = float(extracted.get("confidence_score", 0.0) or 0.0)
            # Priority order is already 8-K -> 10-Q -> 10-K, so early-exit once quality is strong.
            if confidence >= 0.55:
                break

        selected = select_best_guidance(candidates)
        if selected and self.cache:
            try:
                self.cache.set(CacheType.SEC_RESPONSE, cache_key, selected)
            except Exception as exc:
                self.logger.debug(
                    "[SEC Agent] Failed to cache forward guidance for %s: %s",
                    symbol,
                    exc,
                )
        return selected

    @staticmethod
    def _is_weak_guidance_payload(payload: dict[str, Any]) -> bool:
        """
        Determine whether deterministic guidance output is too weak to trust on its own.

        Weak payloads are still kept, but should trigger LLM enrichment.
        """
        if not isinstance(payload, dict) or not payload:
            return True

        has_revenue_range = bool(payload.get("revenue_guidance"))
        has_eps_range = bool(payload.get("eps_guidance"))
        has_any_range = has_revenue_range or has_eps_range
        if has_any_range:
            return False

        confidence_raw = payload.get("confidence_score")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0

        growth_values: list[float] = []
        for key in ("revenue_growth_guidance", "earnings_growth_guidance"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                growth_values.append(float(value))
            except (TypeError, ValueError):
                continue

        if not growth_values:
            return True

        has_only_zero_growth = all(abs(v) < 1e-9 for v in growth_values)
        return confidence < 0.35 or has_only_zero_growth

    async def _extract_forward_guidance_with_llm(
        self,
        *,
        symbol: str,
        form_type: str,
        filing_date: str | None,
        filing_url: str | None,
        filing_text: str,
    ) -> dict[str, Any]:
        """
        LLM fallback for extracting forward guidance from filing text.

        Returns normalized payload compatible with deterministic extractor output.
        """
        if not filing_text or not getattr(self, "ollama", None):
            return {}

        focus_text = self._prepare_guidance_focus_text(filing_text, form_type=form_type)
        if not focus_text or len(focus_text) < 200:
            return {}

        prompt = f"""
Extract ONLY explicit management forward-looking guidance from this SEC filing text.

Return strict JSON with this schema:
{{
  "is_explicit_guidance": true|false,
  "revenue_guidance": {{
    "low": number|null,
    "high": number|null,
    "mid": number|null,
    "horizon": "1q"|"2q"|"3q"|"1y"|null
  }},
  "eps_guidance": {{
    "low": number|null,
    "high": number|null,
    "mid": number|null,
    "horizon": "1q"|"2q"|"3q"|"1y"|null
  }},
  "revenue_growth_guidance": number|null,
  "earnings_growth_guidance": number|null,
  "evidence_snippets": ["short quote 1", "short quote 2"]
}}

Rules:
- Use only explicit company guidance/outlook/forecast/expectation, not analyst estimates.
- Convert percentages to decimal ratio (e.g., 12% -> 0.12).
- Keep revenue/EPS range values in numeric form from the text.
- If guidance is absent or vague, set is_explicit_guidance=false and fields null.
- Output JSON only.

FILING TYPE: {form_type}
FILING DATE: {filing_date}
TEXT:
{focus_text[:24000]}
"""

        try:
            response = await self.ollama.generate(
                model=self.models["analysis"],
                prompt=prompt,
                system="You extract explicit forward guidance from SEC filings with strict JSON output.",
                format="json",
                prompt_name="_extract_forward_guidance_llm_prompt",
            )
            await self._cache_llm_response(
                response=response,
                model=self.models["analysis"],
                symbol=symbol,
                llm_type="sec_forward_guidance_extraction",
                prompt=prompt,
                temperature=0.1,
                top_p=0.9,
                format="json",
                period=filing_date,
                form_type=form_type,
            )
        except Exception as exc:
            self.logger.debug(
                "[SEC Agent] LLM guidance fallback failed for %s %s: %s",
                symbol,
                form_type,
                exc,
            )
            return {}

        normalized = self._normalize_llm_guidance_payload(
            response=response,
            form_type=form_type,
            filing_date=filing_date,
            filing_url=filing_url,
        )
        if normalized:
            self.logger.info(
                "[SEC Agent] LLM guidance fallback extracted signal for %s %s (confidence=%.2f)",
                symbol,
                form_type,
                float(normalized.get("confidence_score", 0.0) or 0.0),
            )
        else:
            self.logger.debug(
                "[SEC Agent] LLM guidance fallback produced no explicit guidance for %s %s",
                symbol,
                form_type,
            )
        return normalized

    def _prepare_guidance_focus_text(self, filing_text: str, *, form_type: str) -> str:
        """
        Reduce filing text to guidance-relevant regions to improve extraction precision.
        """
        text = (filing_text or "").strip()
        if not text:
            return ""

        # Normalize whitespace to avoid huge prompt bloat.
        normalized = re.sub(r"\s+", " ", text)

        # For 10-Q/10-K, prioritize MD&A region (Item 2 for 10-Q, Item 7 for 10-K).
        form_norm = str(form_type or "").upper()
        if form_norm in {"10-Q", "10-K"}:
            item_pattern = r"Item\s+2\." if form_norm == "10-Q" else r"Item\s+7\."
            match = re.search(item_pattern, normalized, flags=re.IGNORECASE)
            if match:
                start = match.start()
                tail = normalized[start : start + 35000]
                if tail:
                    return tail

        # Generic fallback: windows around guidance-related keywords.
        windows: list[str] = []
        for m in re.finditer(
            r"(guidance|outlook|forecast|expects|expectation|raise[d]?|reaffirm|provided?)",
            normalized,
            flags=re.IGNORECASE,
        ):
            left = max(0, m.start() - 900)
            right = min(len(normalized), m.end() + 900)
            windows.append(normalized[left:right])
            if len(windows) >= 8:
                break

        if windows:
            return "\n".join(windows)
        return normalized[:25000]

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(str(value).replace(",", "").strip())
            if math.isnan(parsed):
                return None
            return parsed
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_horizon(value: Any) -> str | None:
        if value is None:
            return None
        raw = str(value).strip().lower()
        if raw in {"1q", "2q", "3q", "1y"}:
            return raw
        if "quarter" in raw or raw in {"q1", "q2", "q3", "q4"}:
            return "1q"
        if "year" in raw or "fy" in raw or "annual" in raw:
            return "1y"
        return None

    def _normalize_guidance_range(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        low = self._to_float_or_none(payload.get("low"))
        high = self._to_float_or_none(payload.get("high"))
        mid = self._to_float_or_none(payload.get("mid"))
        if mid is None and low is not None and high is not None:
            mid = (low + high) / 2.0
        if low is not None and high is not None and low > high:
            low, high = high, low

        if low is None and high is None and mid is None:
            return None

        normalized: dict[str, Any] = {
            "low": low,
            "high": high,
            "mid": mid,
            "horizon": self._normalize_horizon(payload.get("horizon")) or "1y",
        }
        evidence = payload.get("evidence")
        if evidence:
            normalized["snippet"] = str(evidence)[:280]
        return normalized

    def _normalize_llm_guidance_payload(
        self,
        *,
        response: Any,
        form_type: str,
        filing_date: str | None,
        filing_url: str | None,
    ) -> dict[str, Any]:
        """
        Normalize LLM JSON output to canonical guidance payload.
        """
        payload = response
        if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
            payload = payload.get("response")
        if not isinstance(payload, dict):
            return {}

        explicit = payload.get("is_explicit_guidance")
        if explicit is False:
            return {}

        revenue_guidance = self._normalize_guidance_range(payload.get("revenue_guidance"))
        eps_guidance = self._normalize_guidance_range(payload.get("eps_guidance"))
        revenue_growth = self._to_float_or_none(payload.get("revenue_growth_guidance"))
        earnings_growth = self._to_float_or_none(payload.get("earnings_growth_guidance"))

        # Convert percentage-like values to ratio.
        if revenue_growth is not None and abs(revenue_growth) > 2.0:
            revenue_growth /= 100.0
        if earnings_growth is not None and abs(earnings_growth) > 2.0:
            earnings_growth /= 100.0

        if not any(
            [
                revenue_guidance,
                eps_guidance,
                revenue_growth is not None,
                earnings_growth is not None,
            ]
        ):
            return {}

        confidence = 0.0
        if revenue_guidance:
            confidence += 0.40
        if eps_guidance:
            confidence += 0.35
        if revenue_growth is not None:
            confidence += 0.15
        if earnings_growth is not None:
            confidence += 0.10

        normalized: dict[str, Any] = {
            "source": "sec_filing_llm",
            "source_form": str(form_type or "").upper(),
            "filing_date": filing_date,
            "filing_url": filing_url,
            "confidence_score": round(min(confidence, 1.0), 2),
        }
        if revenue_guidance:
            normalized["revenue_guidance"] = revenue_guidance
        if eps_guidance:
            normalized["eps_guidance"] = eps_guidance
        if revenue_growth is not None:
            normalized["revenue_growth_guidance"] = revenue_growth
        if earnings_growth is not None:
            normalized["earnings_growth_guidance"] = earnings_growth

        snippets = payload.get("evidence_snippets")
        if isinstance(snippets, list):
            normalized["evidence_snippets"] = [str(s)[:220] for s in snippets[:3]]

        return normalized

    def _resolve_force_refresh(self, symbol: str | None, task: AgentTask) -> bool:
        """Resolve whether this SEC task should bypass raw cache reuse."""
        # Task-level override (used by tests/legacy task submitters)
        if bool(task.context.get("force_refresh", False)):
            return True

        symbol_upper = (symbol or "").upper()

        # Instance-level override from CacheManager (set by cli_orchestrator --force-refresh).
        cache_manager = getattr(self, "cache", None)
        if cache_manager is not None:
            should_force_refresh = getattr(cache_manager, "_should_force_refresh", None)
            if callable(should_force_refresh):
                try:
                    if bool(should_force_refresh(symbol)):
                        return True
                except Exception:
                    # Fall through to direct override attribute checks.
                    logger.debug("_resolve_force_refresh: suppressed error", exc_info=True)

            override_enabled = bool(getattr(cache_manager, "_force_refresh_override", False))
            if override_enabled:
                override_symbols = getattr(cache_manager, "_force_refresh_symbols_override", None)
                if not override_symbols:
                    return True
                normalized_symbols = {str(s).upper() for s in override_symbols}
                if symbol_upper in normalized_symbols:
                    return True

        # Global CLI-configured override (set by analyze --force-refresh)
        cfg = get_config()
        cache_control = getattr(cfg, "cache_control", None)
        if not cache_control or not getattr(cache_control, "force_refresh", False):
            return False

        forced_symbols = getattr(cache_control, "force_refresh_symbols", None) or []
        if not forced_symbols:
            return True

        return symbol_upper in {str(s).upper() for s in forced_symbols}

    async def _fetch_and_cache_companyfacts(
        self, symbol: str, *, process_raw: bool = True, force_refresh: bool = False
    ) -> dict:
        """
        Fetch RAW SEC CompanyFacts API data and cache in sec_companyfacts_raw table (3-table architecture)

        This is the SINGLE SOURCE OF TRUTH for SEC data in the system.
        All other agents read from this cache - NO duplicate API calls.

        Args:
            symbol: Stock ticker symbol
            process_raw: When False, skip SECDataProcessor step (raw cache only)
            force_refresh: When True, bypass 90-day raw cache reuse and call SEC API

        FLOW:
        1. Check sec_companyfacts_raw table for cached data
        2. If missing/stale, fetch from SEC API
        3. Save raw response to sec_companyfacts_raw
        4. Trigger processing → sec_companyfacts_processed (NEW: using SECDataProcessor)
        5. Return raw data for immediate use

        Returns:
            Raw CompanyFacts data with us-gaap structure intact
        """
        from sqlalchemy import text

        from investigator.infrastructure.database.db import get_db_manager
        from investigator.infrastructure.database.ticker_mapper import TickerCIKMapper
        from investigator.infrastructure.sec.data_processor import SECDataProcessor

        # Step 1: Check if we have fresh cached data in sec_companyfacts_raw
        db_manager = get_db_manager()
        current_price: float | None = None
        if process_raw:
            current_price = await self._fetch_current_price(symbol)

        with db_manager.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, companyfacts, fetched_at
                    FROM sec_companyfacts_raw
                    WHERE symbol = :symbol
                    ORDER BY fetched_at DESC
                    LIMIT 1
                """),
                {"symbol": symbol},
            ).fetchone()

            # If we have data and it's fresh (< 90 days), use it unless force_refresh is set.
            if result:
                from datetime import datetime

                fetched_at = result.fetched_at
                age_days = (datetime.now() - fetched_at).days if fetched_at else 999

                if force_refresh:
                    self.logger.info(
                        "[SEC Agent] Force refresh enabled for %s - bypassing %s-day cached raw data",
                        symbol,
                        age_days,
                    )
                elif age_days < 90:
                    self.logger.info(f"[SEC Agent] Using cached raw data for {symbol} ({age_days} days old)")

                    # Check if processed data exists, if not trigger processing
                    proc_result = conn.execute(
                        text("""
                            SELECT COUNT(*) as count
                            FROM sec_companyfacts_processed
                            WHERE symbol = :symbol
                        """),
                        {"symbol": symbol},
                    ).fetchone()

                    if proc_result.count == 0 and process_raw:
                        self.logger.info(f"[SEC Agent] Processed data missing, triggering processing for {symbol}")
                        processor = SECDataProcessor(db_engine=db_manager.engine)
                        processor.process_raw_data(
                            symbol=symbol,
                            raw_data=result.companyfacts,
                            raw_data_id=result.id,
                            extraction_version="3.0.0_clean_arch",
                            current_price=current_price,
                        )

                    return result.companyfacts

        # Step 2: No cache or stale - fetch from SEC API
        self.logger.info(f"[SEC Agent] Fetching fresh data from SEC API for {symbol}")

        # Get CIK
        mapper = TickerCIKMapper()
        cik = mapper.get_cik(symbol)
        if not cik:
            raise ValueError(f"No CIK found for {symbol}")

        cik_padded = cik.zfill(10)

        # Fetch from SEC API

        api_data = await self.sec_client.get_company_facts(cik_padded)

        if not api_data or "facts" not in api_data:
            raise ValueError(f"SEC API returned no data for {symbol}")

        # Validate us-gaap structure
        if "us-gaap" not in api_data.get("facts", {}):
            self.logger.error(
                f"[SEC Agent] SEC API response for {symbol} missing us-gaap structure! "
                f"Keys: {list(api_data.get('facts', {}).keys())}"
            )
            raise ValueError(f"Invalid SEC API response for {symbol}: missing us-gaap structure")

        us_gaap_tag_count = len(api_data["facts"]["us-gaap"])
        self.logger.info(
            f"[SEC Agent] ✅ Fetched raw CompanyFacts from SEC API: {symbol} has {us_gaap_tag_count} us-gaap tags"
        )

        # Step 3: Save to sec_companyfacts_raw (with hash-based deduplication)
        raw_data_dict = {
            "symbol": symbol,
            "cik": cik_padded,
            "entityName": api_data.get("entityName", ""),
            "facts": api_data.get("facts", {}),
        }

        import hashlib
        import json

        new_data_json = json.dumps(raw_data_dict, sort_keys=True)
        new_data_hash = hashlib.sha256(new_data_json.encode()).hexdigest()
        raw_snapshot_path = self._persist_raw_companyfacts(
            symbol=symbol,
            cik=cik_padded,
            payload=raw_data_dict,
            hash_suffix=new_data_hash[:12],
        )
        self.logger.debug("[SEC Agent] Raw SEC payload cached at %s", raw_snapshot_path)

        data_changed = False  # Track if raw payload changed
        should_reprocess = bool(force_refresh)  # Force refresh should rebuild processed rows

        with db_manager.engine.connect() as conn:
            # Check if existing data has same hash
            existing = conn.execute(
                text("""
                    SELECT id, companyfacts
                    FROM sec_companyfacts_raw
                    WHERE symbol = :symbol
                """),
                {"symbol": symbol},
            ).fetchone()

            if existing:
                existing_json = (
                    existing.companyfacts
                    if isinstance(existing.companyfacts, str)
                    else json.dumps(existing.companyfacts)
                )
                existing_hash = hashlib.sha256(existing_json.encode()).hexdigest()

                if existing_hash == new_data_hash:
                    self.logger.info(
                        f"[SEC Agent] ℹ️  Data unchanged for {symbol} (hash: {new_data_hash[:8]}...), "
                        f"skipping database update"
                    )
                    raw_id = existing.id
                    data_changed = False
                    if force_refresh:
                        self.logger.info(
                            "[SEC Agent] 🔄 Force refresh enabled for %s - reprocessing unchanged raw payload",
                            symbol,
                        )
                else:
                    self.logger.info(
                        f"[SEC Agent] 🔄 Data changed for {symbol} "
                        f"(old: {existing_hash[:8]}..., new: {new_data_hash[:8]}...), updating database"
                    )
                    result = conn.execute(
                        text("""
                            UPDATE sec_companyfacts_raw
                            SET companyfacts = :companyfacts, fetched_at = NOW()
                            WHERE symbol = :symbol
                            RETURNING id
                        """),
                        {"symbol": symbol, "companyfacts": new_data_json},
                    )
                    conn.commit()
                    raw_id = result.fetchone().id
                    data_changed = True
                    should_reprocess = True
                    self.logger.info(f"[SEC Agent] ✅ Updated raw data in sec_companyfacts_raw (id={raw_id})")
            else:
                # No existing data, insert new
                result = conn.execute(
                    text("""
                        INSERT INTO sec_companyfacts_raw (symbol, cik, companyfacts, fetched_at)
                        VALUES (:symbol, :cik, :companyfacts, NOW())
                        RETURNING id
                    """),
                    {
                        "symbol": symbol,
                        "cik": cik_padded,
                        "companyfacts": new_data_json,
                    },
                )
                conn.commit()
                raw_id = result.fetchone().id
                data_changed = True
                should_reprocess = True
                self.logger.info(f"[SEC Agent] ✅ Inserted raw data into sec_companyfacts_raw (id={raw_id})")

        # Step 4: Process raw data into sec_companyfacts_processed when changed OR force-refresh requested
        if process_raw and should_reprocess:
            if force_refresh and not data_changed:
                self.logger.info(
                    "[SEC Agent] Processing raw data with SECDataProcessor for %s (force-refresh rebuild)",
                    symbol,
                )
            else:
                self.logger.info(f"[SEC Agent] Processing raw data with SECDataProcessor for {symbol}")
            processor = SECDataProcessor(db_engine=db_manager.engine)

            processed_filings = processor.process_raw_data(
                symbol=symbol,
                raw_data=raw_data_dict,
                raw_data_id=raw_id,
                extraction_version="3.0.0_clean_arch",
                current_price=current_price,
            )

            self.logger.info(
                f"[SEC Agent] ✅ Processed {len(processed_filings)} filings into sec_companyfacts_processed"
            )
        elif process_raw:
            self.logger.info(f"[SEC Agent] ⏭️  Skipping reprocessing for {symbol} (data unchanged)")
        else:
            self.logger.info(
                "[SEC Agent] Raw caching only for %s complete (processed data step skipped)",
                symbol,
            )

        return raw_data_dict

    def _persist_raw_companyfacts(
        self,
        symbol: str,
        cik: str,
        payload: dict[str, Any],
        hash_suffix: str,
    ) -> Path:
        """Persist raw SEC payloads under data/sec_cache/facts/raw/{symbol}."""
        base_dir = Path("data/sec_cache/facts/raw") / symbol.upper()
        base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"companyfacts_{cik}_{hash_suffix}.json.gz"
        file_path = base_dir / filename

        if file_path.exists():
            return file_path

        try:
            with gzip.open(file_path, "wt", encoding="utf-8", compresslevel=9) as handle:
                json.dump(payload, handle, default=str, separators=(",", ":"))
        except Exception as exc:
            self.logger.warning("Failed to persist raw SEC payload for %s: %s", symbol, exc)
        return file_path

    async def _fetch_current_price(self, symbol: str) -> float | None:
        """Fetch the latest market price from the market data service (best-effort)."""
        if not hasattr(self, "market_data") or self.market_data is None:
            return None

        try:
            quote = await self.market_data.get_quote(symbol)
            price = quote.get("current_price") if quote else None
            if price is not None:
                return float(price)
        except Exception as exc:
            self.logger.warning("⚠️  Unable to fetch current price for %s: %s", symbol, exc)
        return None

    async def _extract_from_filing(self, filing: dict, symbol: str) -> dict:
        """
        Extract financial data directly from filing text using XBRL parser.
        This provides the most timely data (latest filed information).
        """
        financial_data = {}

        try:
            # Try XBRL parsing if available
            if filing.get("xbrl_url"):
                self.logger.info(f"Attempting to fetch and parse XBRL data from {filing.get('xbrl_url')}")

                # Download XBRL content
                import ssl

                import aiohttp

                # SEC.gov is a trusted government website - disable SSL verification
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # SEC requires User-Agent header (per their API guidelines)
                config = get_config()
                sec_config = getattr(config, "sec", None)
                user_agent = getattr(sec_config, "user_agent", "InvestiGator/1.0")

                headers = {
                    "User-Agent": user_agent,
                    "Accept": "application/xml, text/xml, */*",
                }

                connector = aiohttp.TCPConnector(ssl=ssl_context)
                async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                    async with session.get(filing["xbrl_url"], timeout=30) as response:
                        if response.status == 200:
                            xbrl_content = await response.text()

                            # Parse XBRL
                            parsed_xbrl = await self.xbrl_parser.parse_filing(xbrl_content)

                            if parsed_xbrl and parsed_xbrl.get("financial_data"):
                                # Extract metrics from parsed XBRL
                                metrics = await self.xbrl_parser.extract_metrics(parsed_xbrl)

                                if metrics:
                                    # Convert XBRL metrics to our standard format
                                    financial_data = {
                                        "metrics": {
                                            "assets": metrics.get("Assets", 0),
                                            "current_assets": metrics.get("AssetsCurrent", 0),
                                            "liabilities": metrics.get("Liabilities", 0),
                                            "current_liabilities": metrics.get("LiabilitiesCurrent", 0),
                                            "equity": metrics.get("StockholdersEquity") or metrics.get("Equity", 0),
                                            "revenues": metrics.get("Revenues", 0),
                                            "net_income": metrics.get("NetIncomeLoss", 0),
                                            "cash": metrics.get(
                                                "CashAndCashEquivalentsAtCarryingValue",
                                                0,
                                            ),
                                        },
                                        "ratios": {
                                            "current_ratio": metrics.get("CurrentRatio", 0),
                                            "quick_ratio": 0,  # Need to calculate
                                            "debt_to_equity": 0,  # Need to calculate
                                            "debt_to_assets": 0,  # Need to calculate
                                            "roe": 0,  # Need to calculate
                                            "roa": 0,  # Need to calculate
                                            "gross_margin": 0.0,
                                            "operating_margin": 0.0,
                                            "net_margin": 0.0,
                                            "price_to_sales": 0.0,
                                        },
                                        "source": "xbrl_filing",
                                        "data_date": filing.get("filing_date"),
                                    }

                                    # Calculate additional ratios
                                    self._calculate_ratios(financial_data)

                                    self.logger.info(f"Successfully extracted financial data from XBRL for {symbol}")
                                    return financial_data

            # Fallback: Try to extract from filing text using regex patterns
            self.logger.info(f"XBRL not available or failed, attempting text-based extraction for {symbol}")
            financial_data = await self._extract_from_text(filing, symbol)

            if financial_data and financial_data.get("metrics"):
                self.logger.info(f"Successfully extracted financial data from filing text for {symbol}")
                return financial_data

            # If we got here, extraction failed
            raise ValueError("Unable to extract financial data from filing")

        except Exception as e:
            self.logger.warning(f"Filing extraction failed for {symbol}: {e}")
            raise

    async def _extract_from_text(self, filing: dict, symbol: str) -> dict:
        """
        Extract financial data from filing text using regex patterns.
        This is a fallback when XBRL is not available.
        """
        text = filing.get("text", "")
        if not text:
            return {}

        # Simple pattern-based extraction for common financial metrics
        # This is a basic implementation - can be enhanced with more sophisticated patterns
        patterns = {
            "assets": r"Total\s+assets[:\s]+\$?\s*([\d,]+)",
            "liabilities": r"Total\s+liabilities[:\s]+\$?\s*([\d,]+)",
            "equity": r"(?:Total\s+)?(?:stockholders|shareholders)['']?\s+equity[:\s]+\$?\s*([\d,]+)",
            "revenues": r"(?:Total\s+)?(?:revenues?|sales)[:\s]+\$?\s*([\d,]+)",
            "net_income": r"Net\s+income\s+(?:\(loss\))?[:\s]+\$?\s*([\d,\(\)]+)",
        }

        extracted = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value_str = match.group(1).replace(",", "").replace("(", "-").replace(")", "")
                    extracted[key] = float(value_str)
                except (ValueError, AttributeError):
                    pass

        if not extracted:
            return {}

        # Build financial data structure
        financial_data = {
            "metrics": extracted,
            "ratios": {},
            "source": "filing_text_extraction",
            "data_date": filing.get("filing_date"),
        }

        # Calculate ratios if we have the data
        self._calculate_ratios(financial_data)

        return financial_data

    def _calculate_ratios(self, financial_data: dict) -> None:
        """
        Calculate financial ratios from metrics in place.
        """
        metrics = financial_data.get("metrics", {})
        ratios = financial_data.get("ratios", {})

        # Safe division helper
        def safe_div(num, denom, default=0):
            if not num or not denom or denom == 0:
                return default
            return num / denom

        # Current ratio
        if "current_assets" in metrics and "current_liabilities" in metrics:
            ratios["current_ratio"] = safe_div(metrics["current_assets"], metrics["current_liabilities"])

        # Debt to equity
        if "liabilities" in metrics and "equity" in metrics:
            ratios["debt_to_equity"] = safe_div(metrics["liabilities"], metrics["equity"])

        # Debt to assets
        if "liabilities" in metrics and "assets" in metrics:
            ratios["debt_to_assets"] = safe_div(metrics["liabilities"], metrics["assets"])

        # ROE
        if "net_income" in metrics and "equity" in metrics:
            ratios["roe"] = safe_div(metrics["net_income"], metrics["equity"]) * 100

        # ROA
        if "net_income" in metrics and "assets" in metrics:
            ratios["roa"] = safe_div(metrics["net_income"], metrics["assets"]) * 100

        # Net margin
        if "net_income" in metrics and "revenues" in metrics:
            ratios["net_margin"] = safe_div(metrics["net_income"], metrics["revenues"]) * 100

    async def _fetch_filing(self, symbol: str, filing_type: str, period: str) -> SECFilingData:
        """Fetch SEC filing from EDGAR with hybrid data extraction"""
        cache_key = {
            "symbol": symbol,
            "filing_type": filing_type,
            "form_type": filing_type,
            "period": period,
            "category": "filing",
        }

        # Check cache
        from investigator.infrastructure.cache.cache_types import CacheType

        cached = self.cache.get(CacheType.SEC_RESPONSE, cache_key) if self.cache else None
        if cached:
            return SECFilingData(**cached)

        # Fetch from SEC EDGAR
        filing = await self.sec_client.get_filing_by_symbol(symbol, filing_type, period)

        # CLEAN ARCHITECTURE NOTE:
        # Financial data extraction is NOT the SEC Agent's responsibility.
        # The SEC Agent only fetches and caches raw SEC CompanyFacts data.
        # Financial metrics/ratios should be obtained from:
        #   - Fundamental Agent (reads from sec_companyfacts_processed table)
        #   - Processed by SECDataProcessor (src/investigator/infrastructure/sec/data_processor.py)
        #
        # This filing method is only used for optional filing section analysis (MD&A, Risk Factors).
        # Setting financial_data to empty dict since it's not needed for section extraction.
        financial_data = {
            "note": "Financial data is available via Fundamental Agent from sec_companyfacts_processed table",
            "source": "clean_architecture",
        }
        self.logger.info("[SEC Agent] Filing fetched for section analysis only - financial data via Fundamental Agent")

        filing_data = SECFilingData(
            cik=filing["cik"],
            symbol=symbol,
            filing_type=filing_type,
            filing_date=datetime.fromisoformat(filing["filing_date"]),
            period_end=datetime.fromisoformat(filing["period_end"]),
            form_url=filing["form_url"],
            xbrl_url=filing.get("xbrl_url"),
            raw_text=filing["text"],
            extracted_sections={},
            financial_data=financial_data,
        )

        # Cache for 24 hours
        if self.cache:
            try:
                from investigator.infrastructure.cache.cache_types import CacheType

                cached_data = filing_data.__dict__
                del cached_data["raw_text"]
                self.cache.set(CacheType.SEC_RESPONSE, cache_key, cached_data)
            except Exception as e:
                self.logger.warning(f"Failed to cache filing data: {e}")

        return filing_data

    async def _extract_sections(self, filing_data: SECFilingData) -> dict[str, str]:
        """Extract specific sections from filing text"""
        sections = {}
        text = filing_data.raw_text

        for section_name, pattern in self.section_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                start_idx = match.end()
                # Find next section or end of document
                next_section_idx = len(text)
                for other_pattern in self.section_patterns.values():
                    if other_pattern != pattern:
                        next_match = re.search(
                            other_pattern,
                            text[start_idx:],
                            re.IGNORECASE | re.MULTILINE,
                        )
                        if next_match:
                            next_section_idx = min(next_section_idx, start_idx + next_match.start())

                sections[section_name] = text[start_idx:next_section_idx].strip()

        return sections

    async def _analyze_financials(self, filing_data: SECFilingData, sections: dict[str, str]) -> dict:
        """Analyze financial statements and data"""
        prompt = f"""
        Analyze the following financial data and provide insights:
        
        XBRL Financial Data:
        {json.dumps(filing_data.financial_data, indent=2)[:5000]}
        
        Financial Statements Section:
        {sections.get("financial_statements", "Not available")[:3000]}
        
        Extract and analyze:
        1. Revenue trends and growth
        2. Profitability metrics (margins, ROE, ROA)
        3. Liquidity ratios (current ratio, quick ratio)
        4. Debt and leverage metrics
        5. Cash flow analysis
        6. Key financial risks and concerns
        7. Comparison to previous periods
        
        Provide response as JSON with these sections, wrapped in a markdown code block (```json ... ```).

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        For example:
        ```json
        {
            "revenue_trends_and_growth": {
                "trend": "Upward",
            "growth_rate_yoy": 0.15,
            "commentary": "Revenue has been growing consistently over the past year."
          },
          "profitability_metrics": {
                "net_margin": 0.20,
            "roe": 0.25,
            "roa": 0.15,
            "commentary": "Profitability is strong and improving."
          },
          "liquidity_ratios": {
                "current_ratio": 2.0,
            "quick_ratio": 1.5,
            "commentary": "The company has a strong liquidity position."
          },
          "debt_and_leverage_metrics": {
                "debt_to_equity": 0.5,
            "commentary": "Leverage is at a reasonable level."
          },
          "cash_flow_analysis": {
                "operating_cash_flow": 1000,
            "free_cash_flow": 500,
            "commentary": "The company is generating strong cash flow."
          },
          "key_financial_risks_and_concerns": [
            "Dependence on a single product",
            "Exposure to foreign currency fluctuations"
          ],
          "comparison_to_previous_periods": "Financial performance has improved compared to the previous year."
        }
        ```
        """

        response = await self.ollama.generate(
            model=self.models["analysis"],
            prompt=prompt,
            system="You are a financial analyst specializing in SEC filings. Provide detailed, accurate analysis.",
            format="json",
            prompt_name="_analyze_financials_prompt",
        )

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["analysis"],
            symbol=filing_data.symbol,
            llm_type="sec_financial_analysis",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["analysis"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

    async def _extract_key_metrics(self, filing_data: SECFilingData) -> dict:
        """Extract key financial metrics from XBRL data"""
        metrics = {}
        xbrl = filing_data.financial_data

        # Common GAAP metrics mapping
        metric_mappings = {
            "revenue": [
                "Revenues",
                "SalesRevenueNet",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
            ],
            "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncome"],
            "total_assets": ["Assets", "AssetsCurrent", "AssetsNoncurrent"],
            "total_liabilities": [
                "Liabilities",
                "LiabilitiesCurrent",
                "LiabilitiesNoncurrent",
            ],
            "cash": [
                "CashAndCashEquivalentsAtCarryingValue",
                "Cash",
                "CashAndCashEquivalents",
            ],
            "debt": [
                "LongTermDebt",
                "DebtCurrent",
                "LongTermDebtAndCapitalLeaseObligations",
            ],
            "equity": [
                "StockholdersEquity",
                "ShareholdersEquity",
                "CommonStockholdersEquity",
            ],
            "eps": [
                "EarningsPerShareBasic",
                "EarningsPerShareDiluted",
                "EarningsPerShare",
            ],
            "shares_outstanding": [
                "CommonStockSharesOutstanding",
                "WeightedAverageNumberOfSharesOutstandingBasic",
            ],
        }

        for metric_name, possible_keys in metric_mappings.items():
            for key in possible_keys:
                if key in xbrl:
                    metrics[metric_name] = xbrl[key]
                    break

        # Calculate derived metrics
        if "revenue" in metrics and "net_income" in metrics:
            metrics["net_margin"] = metrics["net_income"] / metrics["revenue"] if metrics["revenue"] else 0

        if "total_assets" in metrics and "total_liabilities" in metrics:
            metrics["book_value"] = metrics["total_assets"] - metrics["total_liabilities"]

        if "debt" in metrics and "equity" in metrics:
            metrics["debt_to_equity"] = metrics["debt"] / metrics["equity"] if metrics["equity"] else 0

        return metrics

    async def _analyze_risks(self, risk_section: str, symbol: str) -> list[dict]:
        """Analyze risk factors from filing"""
        if not risk_section:
            return []

        prompt = f"""
        Analyze the following risk factors from an SEC filing and categorize them:

        {risk_section[:5000]}

        Categorize risks into:
        1. Market risks
        2. Operational risks
        3. Financial risks
        4. Regulatory/Legal risks
        5. Technology risks
        6. Competitive risks
        7. Macroeconomic risks

        For each risk, provide:
        - category
        - description
        - severity (high/medium/low)
        - potential_impact
        - mitigation_mentioned (yes/no)

        Return as JSON array of risk objects, wrapped in a markdown code block (```json ... ```).

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        For example:
        ```json
        [
          {
            "category": "Market risks",
            "description": "The company is exposed to fluctuations in commodity prices.",
            "severity": "high",
            "potential_impact": "A significant increase in commodity prices could negatively impact the company's profitability.",
            "mitigation_mentioned": "yes"
          }
        ]
        ```
        """

        response = await self.ollama.generate(
            model=self.models["extraction"],
            prompt=prompt,
            system="Extract and categorize investment risks accurately.",
            format="json",
            prompt_name="_analyze_risks_prompt",
        )

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["extraction"],
            symbol=symbol,
            llm_type="sec_risk_analysis",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

        # Extract risks list from response
        if isinstance(response, dict):
            risks = response.get("risks", [])
        else:
            risks = []

        return self._wrap_llm_response(
            response=risks,
            model=self.models["extraction"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

    async def _analyze_mda(self, mda_section: str, symbol: str) -> dict:
        """Analyze Management Discussion & Analysis"""
        if not mda_section:
            return {}

        prompt = f"""
        Analyze the Management Discussion and Analysis section:

        {mda_section[:5000]}

        Extract and summarize:
        1. Management's view on performance
        2. Key business drivers mentioned
        3. Future outlook and guidance
        4. Strategic initiatives
        5. Challenges and opportunities
        6. Capital allocation priorities
        7. Tone sentiment (positive/neutral/negative)

        Provide structured JSON response, wrapped in a markdown code block (```json ... ```).

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        For example:
        ```json
        {
            "management_view_on_performance": "Management is pleased with the company's performance, highlighting strong revenue growth and margin expansion.",
          "key_business_drivers": [
            "Strong product demand",
            "Market expansion"
          ],
          "future_outlook_and_guidance": "Management expects continued growth in the next quarter, with revenue guidance of $110-$115 million.",
          "strategic_initiatives": [
            "Investing in new product development",
            "Expanding into new geographic markets"
          ],
          "challenges_and_opportunities": {
                "challenges": [
              "Increased competition",
              "Supply chain disruptions"
            ],
            "opportunities": [
              "Growing demand for the company's products",
              "Expansion into new markets"
            ]
          },
          "capital_allocation_priorities": [
            "Reinvesting in the business",
            "Returning capital to shareholders through dividends and share buybacks"
          ],
          "tone_sentiment": "positive"
        }
        ```
        """

        response = await self.ollama.generate(
            model=self.models["analysis"],
            prompt=prompt,
            system="Analyze management commentary for investment insights.",
            format="json",
            prompt_name="_analyze_mda_prompt",
        )

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["analysis"],
            symbol=symbol,
            llm_type="sec_mda_analysis",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["analysis"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

    async def _synthesize_report(self, analysis_data: dict) -> dict:
        """Synthesize comprehensive SEC analysis report"""
        symbol = analysis_data.get("symbol", "UNKNOWN")

        prompt = f"""
        Synthesize a comprehensive investment analysis report from SEC filing data:

        {json.dumps(analysis_data, indent=2)[:8000]}

        Create a structured report with:
        1. Executive Summary (key takeaways)
        2. Financial Performance Analysis
        3. Risk Assessment Summary
        4. Management Commentary Insights
        5. Investment Implications
        6. Red Flags or Concerns
        7. Positive Indicators
        8. Overall Investment Rating (1-10)
        9. Recommendation (buy/hold/sell/avoid)

        Be objective, thorough, and highlight both opportunities and risks.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return as structured JSON, wrapped in a markdown code block (```json ... ```). For example:
        ```json
        {
            "executive_summary": "The company is a market leader with strong growth prospects and a wide economic moat. The stock is currently undervalued and offers an attractive risk/reward profile.",
          "financial_performance_analysis": "The company has a strong financial profile, with a history of consistent revenue growth, expanding margins, and strong cash flow generation.",
          "risk_assessment_summary": "The main risks to our thesis are increased competition, regulatory changes, and a slowdown in the overall economy.",
          "management_commentary_insights": "Management is optimistic about the company's future prospects, highlighting strong product demand and market expansion.",
          "investment_implications": "The stock is an attractive investment for long-term investors with a moderate risk tolerance.",
          "red_flags_or_concerns": [
            "Dependence on a single product"
          ],
          "positive_indicators": [
            "Strong revenue growth",
            "Expanding margins"
          ],
          "overall_investment_rating": 8,
          "recommendation": "buy"
        }
        ```
        """

        response = await self.ollama.generate(
            model=self.models["analysis"],
            prompt=prompt,
            system="You are a senior investment analyst providing comprehensive SEC filing analysis.",
            format="json",
            prompt_name="_synthesize_report_prompt",
        )

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["analysis"],
            symbol=symbol,
            llm_type="sec_synthesis",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["analysis"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

    async def analyze_peer_comparison(self, symbol: str, peers: list[str], filing_type: str = "10-K") -> dict:
        """Compare SEC filings across peer companies"""
        analyses = {}

        # Analyze all companies in parallel
        tasks = []
        for company in [symbol] + peers:
            from investigator.domain.agents.base import AnalysisType, Priority

            task = AgentTask(
                task_id=f"sec_{company}_{filing_type}",
                symbol=company,
                analysis_type=AnalysisType.SEC_FUNDAMENTAL,
                priority=Priority.MEDIUM,
                context={"symbol": company, "filing_type": filing_type},
            )
            tasks.append(self.run(task))

        results = await asyncio.gather(*tasks)

        # Structure results
        for i, company in enumerate([symbol] + peers):
            analyses[company] = results[i]

        # Generate comparative analysis
        comparison = await self._generate_peer_comparison(analyses)

        return {
            "target": symbol,
            "peers": peers,
            "analyses": analyses,
            "comparison": comparison,
        }

    async def _generate_peer_comparison(self, analyses: dict) -> dict:
        """Generate comparative analysis across peers"""
        # Extract symbol list for cache key (use first symbol as primary)
        symbols = list(analyses.keys())
        primary_symbol = symbols[0] if symbols else "UNKNOWN"

        prompt = f"""
        Compare the following SEC filing analyses across peer companies:

        {json.dumps(analyses, indent=2)[:10000]}

        Provide comparative analysis:
        1. Financial performance ranking
        2. Risk profile comparison
        3. Growth trajectory comparison
        4. Profitability comparison
        5. Balance sheet strength ranking
        6. Management quality assessment
        7. Competitive positioning
        8. Best investment opportunity and why

        Return structured JSON comparison, wrapped in a markdown code block (```json ... ```).

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        For example:
        ```json
        {
            "financial_performance_ranking": [
            {"company": "AAPL", "rank": 1 },
            {"company": "MSFT", "rank": 2 },
            {"company": "GOOGL", "rank": 3 }
          ],
          "risk_profile_comparison": {
                "AAPL": "Low",
            "MSFT": "Low",
            "GOOGL": "Medium"
          },
          "growth_trajectory_comparison": {
                "AAPL": "High",
            "MSFT": "Medium",
            "GOOGL": "High"
          },
          "profitability_comparison": {
                "AAPL": "High",
            "MSFT": "High",
            "GOOGL": "Medium"
          },
          "balance_sheet_strength_ranking": [
            {"company": "MSFT", "rank": 1 },
            {"company": "AAPL", "rank": 2 },
            {"company": "GOOGL", "rank": 3 }
          ],
          "management_quality_assessment": {
                "AAPL": "Excellent",
            "MSFT": "Excellent",
            "GOOGL": "Good"
          },
          "competitive_positioning": {
                "AAPL": "Leader",
            "MSFT": "Leader",
            "GOOGL": "Challenger"
          },
          "best_investment_opportunity": {
                "company": "AAPL",
            "reasoning": "AAPL offers the best combination of growth, profitability, and valuation."
          }
        }
        ```
        """

        response = await self.ollama.generate(
            model=self.models["analysis"],
            prompt=prompt,
            system="Provide objective peer comparison analysis for investment decisions.",
            format="json",
            prompt_name="_generate_peer_comparison_prompt",
        )

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["analysis"],
            symbol=primary_symbol,  # Use primary symbol for peer group comparison
            llm_type="sec_peer_comparison",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["analysis"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
        )
