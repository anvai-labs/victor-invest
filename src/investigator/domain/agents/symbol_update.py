"""
SymbolUpdate Agent - Maintains symbol table with latest fundamental metrics

This agent runs after SEC and Fundamental agents to update the symbol table
with absolute financial values (not per-share) that can be used for dynamic
ratio calculations.

Architecture:
- Runs after SEC + Fundamental agents complete
- Uses separate credentials (stockuser/${STOCK_DB_PASSWORD}) to update stock database
- Updates only absolute values (revenue, income, assets, etc.)
- Ratios calculated dynamically: P/E = price / (net_income/shares)

Data Flow:
    SEC Agent → Fundamental Agent → SymbolUpdate Agent
         ↓              ↓                    ↓
    CIK, SIC    TTM Metrics         Update symbol table
"""

import json
import logging
import math
import os
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from investigator.config import get_config
from investigator.domain.agents.base import AgentResult, AgentTask, InvestmentAgent
from investigator.domain.models import TaskStatus

logger = logging.getLogger(__name__)


class SymbolUpdateAgent(InvestmentAgent):
    """
    Agent responsible for maintaining the symbol table with fundamental metrics.

    Updates absolute financial values (not per-share) that can be combined with
    price and shares outstanding for dynamic ratio calculation.

    Attributes:
        stock_engine: SQLAlchemy engine for stock database connection
    """

    def __init__(self, agent_id: str, ollama_client=None, event_bus=None, cache_manager=None):
        """
        Initialize SymbolUpdate agent.

        Args:
            agent_id: Unique identifier for this agent instance
            ollama_client: Ollama client (not used by this agent, can be None)
            event_bus: Event bus (not used by this agent, can be None)
            cache_manager: Cache manager (not used by this agent)
        """
        super().__init__(
            agent_id=agent_id,
            ollama_client=ollama_client or self._create_dummy_client(),
            event_bus=event_bus or self._create_dummy_event_bus(),
            cache_manager=cache_manager,
        )
        self.stock_engine: Engine | None = None
        self.logger = logging.getLogger(f"agent.{agent_id}")

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Best-effort numeric conversion for optional analysis payload values."""
        try:
            if value is None:
                return None
            numeric = float(value)
            if math.isnan(numeric):
                return None
            return numeric
        except (TypeError, ValueError):
            return None

    def _is_suspicious_fair_value(
        self,
        *,
        current_price: float | None,
        fair_value: float | None,
        model_agreement: float | None,
    ) -> bool:
        """
        Return whether a per-share fair value is too far from current price to persist.

        High model agreement can still reflect all models sharing stale split-adjusted
        inputs. Keep the guard conservative and only block values that match the same
        outlier thresholds used by the ranking UI.
        """
        if current_price is None or fair_value is None or current_price <= 0 or fair_value <= 0:
            return False
        if model_agreement is None or model_agreement < 0.7:
            return False

        target_multiple = fair_value / current_price
        return target_multiple >= 4.0 or target_multiple <= 0.25

    def _create_dummy_client(self):
        """Create a dummy ollama client since SymbolUpdate doesn't use LLMs."""

        class DummyClient:
            async def generate(self, *args, **kwargs):
                raise NotImplementedError("SymbolUpdate agent does not use LLM")

        return DummyClient()

    def _create_dummy_event_bus(self):
        """Create a dummy event bus since SymbolUpdate doesn't emit events."""

        class DummyEventBus:
            def emit(self, *args, **kwargs):
                pass

        return DummyEventBus()

    def register_capabilities(self) -> dict[str, Any]:
        """
        Register agent capabilities.

        Returns:
            Dict describing agent capabilities
        """
        return {
            "name": "SymbolUpdate",
            "description": "Updates symbol table with fundamental metrics from SEC/Fundamental agents",
            "capabilities": [
                "update_symbol_metrics",
                "extract_ttm_data",
                "update_balance_sheet",
                "maintain_fiscal_period",
            ],
            "dependencies": ["sec", "fundamental"],
            "output_type": "symbol_table_update",
        }

    def _get_stock_engine(self) -> Engine:
        """
        Get or create connection to stock database.

        Uses separate credentials: stockuser/${STOCK_DB_PASSWORD}
        Database: stock on ${DB_HOST:-localhost}

        Returns:
            SQLAlchemy engine for stock database
        """
        if self.stock_engine is None:
            config = get_config()
            # Build stock database URL with separate credentials
            stock_db_password = os.environ.get("STOCK_DB_PASSWORD", "")
            stock_db_url = (
                f"postgresql://stockuser:{stock_db_password}@{config.database.host}:{config.database.port}/stock"
            )
            self.stock_engine = create_engine(
                stock_db_url,
                pool_size=config.database.pool_size,
                max_overflow=config.database.max_overflow,
                echo=False,  # Don't log SQL queries
            )
            self.logger.info("Connected to stock database for symbol updates")

        return self.stock_engine

    async def pre_process(self, task: AgentTask) -> None:
        """
        Validate that we have SEC and fundamental data to process.

        Args:
            task: Agent task containing symbol and context

        Raises:
            ValueError: If required data is missing
        """
        self.logger.info(f"Pre-processing symbol update for {task.symbol}")

        # DEBUG: Log what's in the context
        context_keys = list(task.context.keys()) if task.context else []
        self.logger.info(f"🔍 Context keys available: {context_keys}")

        # Check if we have fundamental data in context
        if not task.context:
            raise ValueError(f"SymbolUpdate agent requires context with fundamental_analysis for {task.symbol}")

        if "fundamental_analysis" not in task.context:
            raise ValueError(
                f"SymbolUpdate agent requires fundamental_analysis in context for {task.symbol}. "
                f"Available keys: {context_keys}"
            )

        # Check if fundamental_analysis is non-empty
        fundamental_data = task.context.get("fundamental_analysis")
        if not fundamental_data or not isinstance(fundamental_data, dict):
            raise ValueError(
                f"SymbolUpdate agent received empty or invalid fundamental_analysis for {task.symbol}. "
                f"Type: {type(fundamental_data)}, Value: {fundamental_data}"
            )

        self.logger.info(
            f"✅ Fundamental data validated: {len(fundamental_data)} keys, "
            f"has valuation: {'valuation' in fundamental_data}, "
            f"has ratios: {'ratios' in fundamental_data}"
        )

        # Check if we have SEC data (optional but recommended)
        sec_data = task.context.get("sec_analysis")
        if not sec_data or not isinstance(sec_data, dict):
            self.logger.warning(f"No SEC data available for {task.symbol}. Will update with fundamental data only.")
        else:
            self.logger.info(f"✅ SEC data validated: {len(sec_data)} keys")

    async def process(self, task: AgentTask) -> AgentResult:
        """
        Update symbol table with fundamental metrics.

        Extracts TTM metrics from fundamental analysis and updates:
        - Revenue, net income, cash flows (TTM)
        - Assets, liabilities, equity (most recent quarter)
        - CIK, sector, industry from SEC data
        - Outstanding shares, market cap

        Args:
            task: Agent task with symbol and analysis context

        Returns:
            AgentResult with update status and metrics written
        """
        symbol = task.symbol
        self.logger.info(f"Updating symbol table for {symbol}")

        try:
            # Extract data from context
            fundamental = task.context.get("fundamental_analysis", {})
            sec_data = task.context.get("sec_analysis", {})

            # Build update payload
            update_data = self._extract_metrics(symbol, fundamental, sec_data)

            if not update_data:
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.COMPLETED,
                    result_data={
                        "status": "skipped",
                        "symbol": symbol,
                        "message": "No metrics to update",
                    },
                    processing_time=0,
                    metadata={"reason": "insufficient_data", "skipped": True},
                )

            # Update symbol table
            rows_updated = self._update_symbol_table(symbol, update_data)

            self.logger.info(
                f"✅ Updated symbol table for {symbol}: {len(update_data)} fields, {rows_updated} row(s) affected"
            )

            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.COMPLETED,
                result_data={
                    "status": "success",
                    "symbol": symbol,
                    "fields_updated": list(update_data.keys()),
                    "fiscal_period": update_data.get("fiscal_period"),
                    "metrics_count": len(update_data),
                    "rows_updated": rows_updated,
                },
                processing_time=0,  # Will be calculated by base class
                metadata={
                    "rows_updated": rows_updated,
                    "update_timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            self.logger.exception(f"Failed to update symbol table for {symbol}")
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                result_data={"status": "error", "symbol": symbol, "error": str(e)},
                processing_time=0,
                error=str(e),
                metadata={"error_type": type(e).__name__},
            )

    def _extract_metrics(self, symbol: str, fundamental: dict, sec_data: dict) -> dict[str, Any]:
        """
        Extract metrics from fundamental and SEC analysis.

        Pulls TTM metrics and most recent quarter data for symbol table update.

        Args:
            symbol: Stock ticker
            fundamental: Fundamental analysis dict
            sec_data: SEC analysis dict

        Returns:
            Dict of column_name: value pairs for UPDATE statement
        """
        update_data: dict[str, Any] = {}

        # Extract valuation data
        valuation = fundamental.get("valuation", {})
        current_price = self._safe_float(valuation.get("current_price") or fundamental.get("current_price"))

        # Market cap and shares
        if "market_cap" in valuation:
            update_data["mktcap"] = int(valuation["market_cap"])

        # === FAIR VALUE ESTIMATES ===
        multi_model_summary = fundamental.get("multi_model_summary", {})
        model_agreement = self._safe_float(multi_model_summary.get("model_agreement_score"))

        # Extract blended fair value (primary)
        fair_value_blended = self._safe_float(fundamental.get("fair_value"))
        skip_fair_values_for_price_mismatch = False
        if fair_value_blended and fair_value_blended > 0:
            if self._is_suspicious_fair_value(
                current_price=current_price,
                fair_value=fair_value_blended,
                model_agreement=model_agreement,
            ):
                skip_fair_values_for_price_mismatch = True
                update_data["divergence_flag"] = True
                self.logger.warning(
                    "%s: skipping suspicious fair_value %.2f versus current_price %.2f",
                    symbol,
                    fair_value_blended,
                    current_price,
                )
            else:
                update_data["fair_value_blended"] = round(float(fair_value_blended), 2)

        # Extract multi-model summary
        if multi_model_summary:
            # Blended fair value (from multi-model orchestrator)
            blended_fv = self._safe_float(multi_model_summary.get("blended_fair_value"))
            if blended_fv and blended_fv > 0:
                if self._is_suspicious_fair_value(
                    current_price=current_price,
                    fair_value=blended_fv,
                    model_agreement=model_agreement,
                ):
                    skip_fair_values_for_price_mismatch = True
                    update_data["divergence_flag"] = True
                    self.logger.warning(
                        "%s: skipping suspicious blended_fair_value %.2f versus current_price %.2f",
                        symbol,
                        blended_fv,
                        current_price,
                    )
                else:
                    update_data["fair_value_blended"] = round(float(blended_fv), 2)

            # Model quality metrics
            agreement = multi_model_summary.get("model_agreement_score")
            if agreement is not None:
                update_data["model_agreement_score"] = round(float(agreement), 4)

            confidence = multi_model_summary.get("overall_confidence")
            if confidence is not None:
                update_data["model_confidence"] = round(float(confidence), 4)

            applicable = multi_model_summary.get("applicable_models")
            if applicable is not None:
                update_data["applicable_models"] = int(applicable)

            divergence = multi_model_summary.get("divergence_flag")
            if divergence is not None:
                update_data["divergence_flag"] = bool(divergence)

            # Individual model fair values
            models = multi_model_summary.get("models", [])
            for model in models:
                if not isinstance(model, dict):
                    continue
                model_name = model.get("model", "").lower()
                fair_value = model.get("fair_value_per_share")
                if (
                    fair_value
                    and fair_value > 0
                    and model.get("applicable")
                    and not skip_fair_values_for_price_mismatch
                ):
                    if model_name == "dcf":
                        update_data["fair_value_dcf"] = round(float(fair_value), 2)
                        # DCF-specific metrics
                        assumptions = model.get("assumptions", {})
                        if "wacc" in assumptions:
                            update_data["wacc"] = round(float(assumptions["wacc"]), 4)
                        if "terminal_growth" in assumptions:
                            update_data["terminal_growth_rate"] = round(float(assumptions["terminal_growth"]), 4)
                        metadata = model.get("metadata", {})
                        if "projection_years" in assumptions:
                            update_data["dcf_projection_years"] = int(assumptions["projection_years"])
                        # Rule of 40 from DCF metadata
                        rule40 = metadata.get("rule_of_40", {})
                        if rule40:
                            score = rule40.get("score")
                            if score is not None:
                                update_data["rule_of_40_score"] = round(float(score), 2)
                            classification = rule40.get("classification")
                            if classification:
                                update_data["rule_of_40_classification"] = str(classification)
                    elif model_name == "ggm":
                        update_data["fair_value_ggm"] = round(float(fair_value), 2)
                    elif model_name == "ps":
                        update_data["fair_value_ps"] = round(float(fair_value), 2)
                    elif model_name == "pe":
                        update_data["fair_value_pe"] = round(float(fair_value), 2)
                    elif model_name == "pb":
                        update_data["fair_value_pb"] = round(float(fair_value), 2)
                    elif model_name == "ev_ebitda":
                        update_data["fair_value_ev_ebitda"] = round(float(fair_value), 2)

            if skip_fair_values_for_price_mismatch:
                multi_model_summary = dict(multi_model_summary)
                multi_model_summary["valuation_quality_flag"] = "split_or_stale_price_mismatch"

            # Store full JSONB for detailed analysis
            update_data["valuation_models_json"] = multi_model_summary

            # NEW: Extract tier classification for queryability
            tier_classification = multi_model_summary.get("tier_classification")
            if tier_classification:
                update_data["tier_classification"] = str(tier_classification)

            # NEW: Extract fallback flag to track when tier-based weights were used
            fallback_applied = multi_model_summary.get("fallback_applied")
            if fallback_applied is not None:
                update_data["fallback_weights_used"] = bool(fallback_applied)

        # LLM fair value estimate (for comparison)
        llm_estimate = fundamental.get("llm_fair_value_estimate")
        if llm_estimate and llm_estimate > 0:
            # Store in JSONB metadata, not as separate column
            if "valuation_models_json" in update_data:
                update_data["valuation_models_json"]["llm_estimate"] = round(float(llm_estimate), 2)

        # === RATIOS ===
        ratios = fundamental.get("ratios", {})
        if ratios:
            # P/S ratio and metrics
            ps_ratio = ratios.get("price_to_sales") or ratios.get("ps_ratio")
            if ps_ratio and ps_ratio > 0:
                update_data["ps_ratio"] = round(float(ps_ratio), 2)

            # P/E ratio
            pe_ratio = ratios.get("pe_ratio") or ratios.get("price_to_earnings")
            if pe_ratio and pe_ratio > 0:
                update_data["pe_ratio"] = round(float(pe_ratio), 2)

            # P/B ratio
            pb_ratio = ratios.get("price_to_book") or ratios.get("pb_ratio")
            if pb_ratio and pb_ratio > 0:
                update_data["pb_ratio"] = round(float(pb_ratio), 2)

            # PEG ratio
            peg_ratio = ratios.get("peg_ratio") or ratios.get("peg")
            if peg_ratio and peg_ratio > 0:
                update_data["peg_ratio"] = round(float(peg_ratio), 2)

            # EV/EBITDA ratio
            ev_ebitda = ratios.get("ev_to_ebitda") or ratios.get("ev_ebitda_ratio")
            if ev_ebitda and ev_ebitda > 0:
                update_data["ev_ebitda_ratio"] = round(float(ev_ebitda), 2)

            # Debt-to-Equity
            dte = ratios.get("debt_to_equity") or ratios.get("debt_equity_ratio")
            if dte is not None:
                update_data["debt_to_equity"] = round(float(dte), 2)

            # FCF margin
            fcf_margin = ratios.get("fcf_margin") or ratios.get("free_cash_flow_margin")
            if fcf_margin is not None:
                update_data["fcf_margin"] = round(float(fcf_margin), 2)

            # Revenue growth rate
            rev_growth = ratios.get("revenue_growth") or ratios.get("revenue_growth_rate")
            if rev_growth is not None:
                update_data["revenue_growth_rate"] = round(float(rev_growth), 2)

        # === SECTOR COMPARISONS ===
        # Get sector median P/S for comparison
        company_profile = valuation.get("company_profile", {})
        if company_profile:
            sector_ps = company_profile.get("sector_median_ps")
            if sector_ps and sector_ps > 0:
                update_data["sector_median_ps"] = round(float(sector_ps), 2)
                # Calculate P/S premium/discount
                if update_data.get("ps_ratio"):
                    ps_premium = ((update_data["ps_ratio"] / sector_ps) - 1) * 100
                    update_data["ps_premium_discount"] = round(ps_premium, 2)

        # Valuation timestamp
        if any(k.startswith("fair_value") for k in update_data):
            update_data["valuation_updated_at"] = datetime.now()

        # Get quarterly data (most recent)
        quarterly_data = fundamental.get("quarterly_data", [])
        if quarterly_data and len(quarterly_data) > 0:
            latest_quarter = quarterly_data[0]  # Assuming sorted newest first
            financial_data = latest_quarter.get("financial_data", {})

            # TTM metrics (trailing twelve months)
            if "revenue" in financial_data:
                update_data["revenue"] = int(financial_data["revenue"])

            if "net_income" in financial_data:
                update_data["net_income"] = int(financial_data["net_income"])

            if "operating_cash_flow" in financial_data:
                update_data["operating_cash_flow"] = int(financial_data["operating_cash_flow"])

            if "free_cash_flow" in financial_data:
                update_data["free_cash_flow"] = int(financial_data["free_cash_flow"])

            if "gross_profit" in financial_data:
                update_data["gross_profit"] = int(financial_data["gross_profit"])

            if "ebitda" in financial_data:
                update_data["ebitda"] = int(financial_data["ebitda"])

            # Balance sheet (most recent quarter)
            if "total_assets" in financial_data:
                update_data["total_assets"] = int(financial_data["total_assets"])

            if "total_liabilities" in financial_data:
                update_data["total_liabilities"] = int(financial_data["total_liabilities"])

            if "stockholders_equity" in financial_data:
                update_data["stockholders_equity"] = int(financial_data["stockholders_equity"])

            if "total_debt" in financial_data:
                update_data["total_debt"] = int(financial_data["total_debt"])

            if "cash_and_cash_equivalents" in financial_data:
                update_data["cash_and_equivalents"] = int(financial_data["cash_and_cash_equivalents"])

            if "dividends_paid" in financial_data:
                update_data["dividends_paid"] = int(financial_data["dividends_paid"])

            # Shares outstanding (use standard shares_outstanding key)
            if "shares_outstanding" in financial_data:
                update_data["outstandingshares"] = int(financial_data["shares_outstanding"])

            # Public float (EntityPublicFloat from SEC DEI namespace is in USD)
            # Convert to float_shares by dividing by current price
            if "public_float_usd" in financial_data:
                public_float_usd = financial_data["public_float_usd"]
                current_price = financial_data.get("current_price", 0)
                if public_float_usd > 0 and current_price > 0:
                    float_shares = int(public_float_usd / current_price)
                    update_data["float_shares"] = float_shares
                    self.logger.info(
                        f"Calculated float_shares: ${public_float_usd:,.0f} / ${current_price:.2f} = {float_shares:,} shares"
                    )

            # Fiscal period
            fiscal_period = latest_quarter.get("fiscal_period")
            fiscal_year = latest_quarter.get("fiscal_year")
            if fiscal_period and fiscal_year:
                update_data["fiscal_period"] = f"{fiscal_year}-{fiscal_period}"

        # Extract SEC data
        if sec_data:
            company_info = sec_data.get("company_info", {})

            if "cik" in company_info:
                update_data["cik"] = int(company_info["cik"])

            if "sector" in company_info:
                update_data["sec_sector"] = company_info["sector"]

            if "industry" in company_info:
                update_data["sec_industry"] = company_info["industry"]

            if "sic" in company_info:
                update_data["sic_code"] = int(company_info["sic"])

        # Add metadata
        if update_data:
            update_data["metrics_updated_at"] = datetime.now()
            update_data["metrics_source"] = "sec_companyfacts"
            update_data["lastupdts"] = datetime.now()

        return update_data

    def _update_symbol_table(self, symbol: str, update_data: dict[str, Any]) -> int:
        """
        Execute UPDATE statement on symbol table.

        Args:
            symbol: Stock ticker (PRIMARY KEY)
            update_data: Dict of column_name: value pairs

        Returns:
            Number of rows updated (should be 1)

        Raises:
            Exception: If UPDATE fails
        """
        if not update_data:
            return 0

        # Serialize JSONB columns to JSON strings
        # PostgreSQL JSONB columns require JSON-encoded strings, not Python dicts
        jsonb_columns = ["valuation_models_json"]
        for col in jsonb_columns:
            if col in update_data and update_data[col] is not None and isinstance(update_data[col], dict):
                update_data[col] = json.dumps(update_data[col])
                self.logger.debug(f"Serialized {col} to JSON string ({len(update_data[col])} chars)")

        # Build SET clause
        set_clause = ", ".join([f"{col} = :{col}" for col in update_data])

        # Build UPDATE statement
        query = text(f"""
            UPDATE symbol
            SET {set_clause}
            WHERE UPPER(ticker) = UPPER(:symbol)
        """)

        # Add symbol to params
        params = {"symbol": symbol, **update_data}

        # Execute update
        engine = self._get_stock_engine()
        with engine.connect() as conn:
            result = conn.execute(query, params)
            conn.commit()
            rows_updated = result.rowcount

        return rows_updated

    async def post_process(self, task: AgentTask, result: AgentResult) -> AgentResult:
        """
        Post-process symbol update result.

        Args:
            task: Agent task being processed
            result: Agent result to post-process

        Returns:
            Processed agent result
        """
        # Log summary
        if result.status == TaskStatus.COMPLETED:
            symbol = task.symbol if task else result.result_data.get("symbol", "unknown")
            metrics_count = result.result_data.get("metrics_count", 0)
            self.logger.info(f"Symbol table updated for {symbol}: {metrics_count} metrics")
        elif result.status == TaskStatus.FAILED:
            symbol = task.symbol if task else result.result_data.get("symbol", "unknown")
            error = result.error or result.result_data.get("error", "Unknown error")
            self.logger.error(f"Symbol update failed for {symbol}: {error}")

        return result

    def __del__(self):
        """Clean up database connection on agent destruction."""
        if hasattr(self, "stock_engine") and self.stock_engine:
            self.stock_engine.dispose()
