"""
Report Payload Builder

Transforms raw synthesis agent output into normalized PDF report payloads.

This module solves the structural mismatch between synthesis agent outputs
(which wrap data in {'response': {...}}) and PDFReportGenerator expectations
(which expect flat recommendation dicts matching InvestmentRecommendation schema).

Key transformations:
- Unwrap LLM response wrappers
- Convert scores (0-100 → 0-10 scale)
- Normalize field names and structures
- Sanitize missing/invalid data
- Provide sensible defaults

Author: InvestiGator Team
Date: 2025-11-02
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReportDataContract:
    """
    Canonical data contract between synthesis agent and PDF generator.

    This ensures both sides understand the expected structure and prevents
    future regressions when either component changes.
    """

    # Core identification
    symbol: str
    timestamp: str

    # Recommendation
    recommendation: str  # 'strong buy', 'buy', 'hold', 'sell', 'strong sell'
    confidence: int  # 0-100

    # Scores (0-10 scale for PDF)
    composite_score: float
    fundamental_score: float
    technical_score: float
    value_score: float = 5.0
    growth_score: float = 5.0
    business_quality_score: float = 5.0

    # Financial metrics
    current_price: float = 0.0
    fair_value: float = 0.0
    price_target_12m: float = 0.0
    market_cap: float = 0.0

    # Investment thesis
    investment_thesis: str = ""
    key_insights: list[str] = field(default_factory=list)
    value_drivers: list[str] = field(default_factory=list)

    # Risk assessment
    risk_assessment: dict[str, Any] = field(default_factory=dict)
    overall_risk: float = 50.0  # 0-100
    primary_risks: list[str] = field(default_factory=list)
    risk_tier: str = "MEDIUM"

    # Scenarios
    scenarios: dict[str, Any] = field(default_factory=dict)
    bull_case: dict | None = None
    base_case: dict | None = None
    bear_case: dict | None = None

    # Action plan
    action_plan: dict[str, Any] = field(default_factory=dict)
    specific_actions: list[str] = field(default_factory=list)

    # Trends and analysis
    multi_year_trends: dict[str, Any] = field(default_factory=dict)
    trend_analysis: dict[str, Any] = field(default_factory=dict)

    # Conflicts and reconciliation
    conflicts: list[str] = field(default_factory=list)
    reconciliation: str = ""

    # Data quality
    data_quality_grade: str = "N/A"
    data_quality_score: float = 0.0

    # Charts
    chart_paths: list[str] = field(default_factory=list)


class ReportPayloadBuilder:
    """
    Builds normalized PDF report payloads from synthesis agent outputs.

    Handles all data transformations, validations, and fallbacks needed
    to convert raw synthesis data into PDF-ready recommendation dicts.
    """

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize the payload builder."""
        self.logger = logger or logging.getLogger(__name__)

    def build(
        self,
        symbol: str,
        synthesis_report: Any,
        fundamental_data: dict | None = None,
        technical_data: dict | None = None,
        chart_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build normalized PDF report payload from synthesis output.

        Args:
            symbol: Stock symbol
            synthesis_report: Raw synthesis agent output
            fundamental_data: Optional fundamental analysis data for backfilling
            technical_data: Optional technical analysis data
            chart_paths: Optional list of chart file paths

        Returns:
            Normalized recommendation dict ready for PDFReportGenerator
        """
        self.logger.info(f"Building PDF payload for {symbol}")

        # Unwrap LLM response if needed (_unwrap_response always returns a dict)
        unwrapped = self._unwrap_response(synthesis_report)

        # Extract core fields
        recommendation = self._extract_recommendation(unwrapped)
        scores = self._extract_scores(unwrapped)
        financials = self._extract_financials(unwrapped, fundamental_data, technical_data)
        thesis = self._extract_thesis(unwrapped)
        risks = self._extract_risks(unwrapped)
        scenarios = self._extract_scenarios(unwrapped)
        action_plan = self._extract_action_plan(unwrapped)

        # Backfill missing critical fields from fundamental and technical data
        if fundamental_data:
            financials = self._backfill_financials(financials, fundamental_data)
            scores = self._backfill_scores(scores, fundamental_data)

        # Backfill from technical data if still missing
        if technical_data:
            financials = self._backfill_from_technical(financials, technical_data)

        # Validate and sanitize
        self._validate_payload(symbol, financials, scores)

        # Build normalized payload
        payload = {
            "symbol": symbol,
            "timestamp": (
                unwrapped.get("timestamp")
                or (synthesis_report.get("timestamp", "") if isinstance(synthesis_report, dict) else "")
            ),
            # Recommendation
            "recommendation": recommendation.get("action", "hold"),
            "confidence": int(recommendation.get("confidence", 50)),
            # Scores (convert to 0-10 scale)
            "composite_score": self._scale_score(scores.get("composite", 50)),
            "fundamental_score": self._scale_score(scores.get("fundamental", 50)),
            "technical_score": self._scale_score(scores.get("technical", 50)),
            "value_score": self._scale_score(scores.get("value", 50)),
            "growth_score": self._scale_score(scores.get("growth", 50)),
            "business_quality_score": self._scale_score(scores.get("quality", 50)),
            # Financials
            "current_price": financials.get("current_price", 0),
            "fair_value": financials.get("fair_value", 0),
            "price_target_12m": financials.get("price_target_12m", 0),
            "market_cap": financials.get("market_cap", 0),
            # Investment thesis
            "investment_thesis": thesis.get("thesis", ""),
            "key_insights": thesis.get("insights", []),
            "value_drivers": thesis.get("drivers", []),
            # Risk assessment
            "risk_assessment": risks,
            "overall_risk": int(risks.get("overall_risk", 50)),
            "primary_risks": risks.get("primary_risks", []),
            "risk_tier": risks.get("tier", "MEDIUM"),
            # Scenarios
            "scenarios": scenarios,
            "bull_case": scenarios.get("bull_case"),
            "base_case": scenarios.get("base_case"),
            "bear_case": scenarios.get("bear_case"),
            # Action plan
            "action_plan": action_plan,
            "specific_actions": action_plan.get("actions", []),
            # Trends
            "multi_year_trends": unwrapped.get("multi_year_trends", {}),
            "trend_analysis": unwrapped.get("trend_analysis", {}),
            # Conflicts
            "conflicts": unwrapped.get("conflicts", []),
            "reconciliation": unwrapped.get("reconciliation", ""),
            # Charts
            "chart_paths": chart_paths or [],
        }

        # Add alias keys that report_generator expects
        # Map composite_score → overall_score for report renderer
        payload["overall_score"] = payload["composite_score"]

        # Initialize financial statement scores (may be backfilled from comprehensive data)
        payload.setdefault("income_score", 0)
        payload.setdefault("cashflow_score", 0)
        payload.setdefault("balance_score", 0)
        payload.setdefault("data_quality_score", 0)

        # Backfill technical indicators from technical_data for PDF rendering
        # (support/resistance levels, trend direction, momentum signals, entry/exit signals)
        if technical_data:
            payload = self._backfill_technical_indicators(payload, technical_data)

        self.logger.info(
            f"✅ Built payload for {symbol}: {recommendation.get('action', 'hold').upper()} "
            f"(composite: {payload['composite_score']:.1f}/10, "
            f"price: ${payload['current_price']:.2f})"
        )

        return payload

    def _unwrap_response(self, synthesis_report: Any) -> dict:
        """Unwrap LLM response wrappers to get actual data."""
        data: Any = synthesis_report

        # Parse JSON strings eagerly (some callers pass serialized payloads).
        if isinstance(data, str):
            parsed = self._parse_json_object(data)
            if parsed is None:
                self.logger.warning(
                    "Synthesis report is string and not JSON object (type=%s). Returning empty payload.",
                    type(synthesis_report),
                )
                return {}
            data = parsed

        if not isinstance(data, dict):
            self.logger.warning(
                "Synthesis report has unsupported type %s. Returning empty payload.",
                type(data),
            )
            return {}

        # Recursively unwrap common envelope shape: {"response": ...}
        max_unwrap_depth = 5
        depth = 0
        while isinstance(data, dict) and "response" in data and depth < max_unwrap_depth:
            wrapped = data.get("response")
            if isinstance(wrapped, dict):
                data = wrapped
                depth += 1
                continue
            if isinstance(wrapped, str):
                if not wrapped.strip():
                    self.logger.warning("Response is empty string - returning empty payload")
                    return {}
                parsed = self._parse_json_object(wrapped)
                if parsed is None:
                    self.logger.warning(
                        "Response is %s, not JSON object - returning empty payload",
                        type(wrapped),
                    )
                    return {}
                data = parsed
                depth += 1
                continue
            self.logger.warning("Response is %s, not dict - returning empty payload", type(wrapped))
            return {}

        # Further unwrap if report key exists and is a dict
        if isinstance(data, dict) and isinstance(data.get("report"), dict):
            return dict(data["report"])

        return data if isinstance(data, dict) else {}

    def _parse_json_object(self, raw: str) -> dict[str, Any] | None:
        """Parse a JSON string and return dict payloads only."""
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

        return parsed if isinstance(parsed, dict) else None

    def _extract_recommendation(self, data: dict) -> dict:
        """Extract recommendation and confidence."""
        rec = data.get("recommendation", {})
        if not rec and isinstance(data.get("recommendation_and_action_plan"), dict):
            rec = data.get("recommendation_and_action_plan", {})

        if isinstance(rec, dict):
            return {
                "action": (
                    rec.get("action")
                    or rec.get("recommendation")
                    or rec.get("final_recommendation")
                    or rec.get("investment_recommendation")
                    or "hold"
                ),
                "confidence": (
                    rec.get("confidence")
                    or rec.get("confidence_level")
                    or data.get("confidence")
                    or data.get("confidence_level")
                    or 50
                ),
            }
        if isinstance(rec, str) and rec.strip():
            return {
                "action": rec.strip(),
                "confidence": data.get("confidence", data.get("confidence_level", 50)),
            }
        if isinstance(data.get("final_recommendation"), str):
            return {
                "action": data.get("final_recommendation", "hold"),
                "confidence": data.get("confidence", data.get("confidence_level", 50)),
            }
        return {"action": "hold", "confidence": 50}

    def _extract_scores(self, data: dict) -> dict:
        """
        Extract all scores from synthesis response.

        Handles multiple field naming conventions:
        - composite_scores.overall_score → composite
        - composite_scores.fundamental_score → fundamental
        - Fallback to analysis_scores if composite_scores missing
        """
        # Try composite_scores first (current synthesis format)
        composite = data.get("composite_scores", {})
        analysis = data.get("analysis_scores", {})

        # Try to get assessment scores as fallback
        assessment = data.get("fundamental_assessment", {})

        return {
            "composite": (
                composite.get("overall_score") or composite.get("composite") or analysis.get("composite", 50)
            ),
            "fundamental": (
                composite.get("fundamental_score")
                or analysis.get("fundamental")
                or assessment.get("financial_health", {}).get("score", 50)
            ),
            "technical": (composite.get("technical_score") or analysis.get("technical", 50)),
            "value": (composite.get("value_score") or analysis.get("value", 50)),
            "growth": (composite.get("growth_score") or analysis.get("growth", 50)),
            "quality": (
                composite.get("business_quality_score") or composite.get("quality_score") or analysis.get("quality", 50)
            ),
        }

    def _extract_financials(
        self,
        data: dict,
        fundamental_data: dict | None,
        technical_data: dict | None,
    ) -> dict:
        """
        Extract financial metrics with comprehensive fallback chain.

        Priority:
        1. Structured synthesis data (valuation dict)
        2. Narrative report appendix (key_metrics_summary)
        3. Fundamental agent data
        """
        valuation = data.get("valuation", {})

        # Try narrative report appendix (where synthesis actually puts the data)
        appendix = data.get("appendix", {})
        key_metrics = appendix.get("key_metrics_summary", {})

        # Helper to parse currency strings like "$270.37" -> 270.37
        def parse_currency(value):
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                # Remove $, commas, B/M/K suffixes
                cleaned = value.replace("$", "").replace(",", "").strip()
                # Handle B/M/K suffixes
                multiplier = 1
                if cleaned.endswith("B"):
                    multiplier = 1_000_000_000
                    cleaned = cleaned[:-1]
                elif cleaned.endswith("M"):
                    multiplier = 1_000_000
                    cleaned = cleaned[:-1]
                elif cleaned.endswith("K"):
                    multiplier = 1_000
                    cleaned = cleaned[:-1]
                try:
                    return float(cleaned) * multiplier
                except ValueError:
                    return 0
            return 0

        # Extract with fallback chain
        financials = {
            "current_price": (
                valuation.get("current_price", 0) or parse_currency(key_metrics.get("current_price", 0)) or 0
            ),
            "fair_value": (valuation.get("fair_value", 0) or parse_currency(key_metrics.get("fair_value", 0)) or 0),
            "price_target_12m": (
                valuation.get("price_target_12m", 0)
                or valuation.get("price_target", 0)
                or parse_currency(key_metrics.get("price_target", 0))
                or 0
            ),
            "market_cap": (data.get("market_cap", 0) or parse_currency(key_metrics.get("market_cap", 0)) or 0),
        }

        # Backfill from fundamental if still missing
        if fundamental_data:
            fund_val = fundamental_data.get("valuation", {})
            fund_analysis_response = fundamental_data.get("analysis", {}).get("response", {})
            fund_ratios = fund_analysis_response.get("ratios", {})
            fund_company_data = fundamental_data.get("analysis", {}).get("company_data", {})

            if financials["current_price"] == 0:
                financials["current_price"] = (
                    fund_val.get("current_price", 0)
                    or fund_ratios.get("current_price", 0)
                    or fund_company_data.get("current_price", 0)
                )
            if financials["fair_value"] == 0:
                financials["fair_value"] = fund_val.get("fair_value", 0)
            if financials["market_cap"] == 0:
                financials["market_cap"] = (
                    fundamental_data.get("market_cap", 0)
                    or fund_company_data.get("market_cap", 0)
                    or fund_ratios.get("market_cap", 0)
                )

        return financials

    def _extract_thesis(self, data: dict) -> dict:
        """
        Extract investment thesis and insights.

        Handles multiple response structures:
        - executive_summary.investment_thesis (current format)
        - investment_thesis (legacy format)
        - Nested dict with summary/thesis keys
        """
        # Try executive_summary first (current synthesis format)
        exec_summary = data.get("executive_summary", {})
        thesis_data = data.get("investment_thesis", {})

        # Handle both string and dict formats
        if exec_summary and isinstance(exec_summary, dict):
            # Current format: executive_summary contains thesis
            thesis = exec_summary.get("investment_thesis", "")
            insights = data.get("key_insights", [])
            drivers: list[Any] = []  # Not always present in executive_summary
        elif isinstance(thesis_data, str):
            # Legacy format: thesis is a direct string
            thesis = thesis_data
            insights = data.get("key_insights", [])
            drivers = []
        elif isinstance(thesis_data, dict):
            # Legacy format: thesis is nested dict
            thesis = thesis_data.get("summary", thesis_data.get("thesis", ""))
            insights = thesis_data.get("key_insights", thesis_data.get("insights", []))
            drivers = list(thesis_data.get("value_drivers") or thesis_data.get("drivers") or [])
        else:
            thesis = ""
            insights = []
            drivers = []

        # If still empty, try fundamental_assessment
        if not thesis:
            fund_assessment = data.get("fundamental_assessment", {})
            if isinstance(fund_assessment, dict):
                thesis = fund_assessment.get("investment_thesis", "")

        return {
            "thesis": thesis,
            "insights": insights if isinstance(insights, list) else [],
            "drivers": drivers if isinstance(drivers, list) else [],
        }

    def _extract_risks(self, data: dict) -> dict:
        """Extract risk assessment."""
        risk_data = data.get("risk_assessment", {})
        if isinstance(risk_data, list):
            return {
                "overall_risk": data.get("risk_score", 50),
                "primary_risks": risk_data[:5],
                "tier": data.get("risk_tier", "MEDIUM"),
            }
        if not isinstance(risk_data, dict):
            risk_data = {}

        return {
            "overall_risk": risk_data.get("overall_risk", risk_data.get("risk_score", 50)),
            "primary_risks": risk_data.get("primary_risks", risk_data.get("risks", [])),
            "tier": risk_data.get("risk_tier", risk_data.get("tier", "MEDIUM")),
        }

    def _extract_scenarios(self, data: dict) -> dict:
        """Extract price scenarios."""
        scenarios = data.get("scenarios", {})
        if not isinstance(scenarios, dict):
            scenarios = {}

        return {
            "bull_case": (scenarios.get("bull_case") or scenarios.get("bull") or data.get("bull_case")),
            "base_case": (scenarios.get("base_case") or scenarios.get("base") or data.get("base_case")),
            "bear_case": (scenarios.get("bear_case") or scenarios.get("bear") or data.get("bear_case")),
        }

    def _extract_action_plan(self, data: dict) -> dict:
        """Extract action plan."""
        action_plan = data.get("action_plan", {})
        if not action_plan and isinstance(data.get("recommendation_and_action_plan"), dict):
            action_plan = data.get("recommendation_and_action_plan", {})
        if not isinstance(action_plan, dict):
            action_plan = {}

        actions = action_plan.get("specific_actions", action_plan.get("actions", []))
        if not actions and isinstance(action_plan.get("entry_strategy"), dict):
            entry = action_plan.get("entry_strategy", {})
            maybe_action = entry.get("entry_timing_considerations")
            actions = [maybe_action] if isinstance(maybe_action, str) and maybe_action else []

        return {
            "actions": actions if isinstance(actions, list) else [],
            "timeframe": action_plan.get("timeframe", ""),
            "monitoring": action_plan.get("monitoring", []),
        }

    def _backfill_financials(self, financials: dict, fundamental_data: dict) -> dict:
        """Backfill missing financials from fundamental analysis."""
        if financials["current_price"] == 0:
            # Try ratios
            ratios = fundamental_data.get("analysis", {}).get("response", {}).get("ratios", {})
            financials["current_price"] = ratios.get("current_price", 0)

        if financials["market_cap"] == 0:
            # Try multiple locations including company_data
            ratios = fundamental_data.get("analysis", {}).get("response", {}).get("ratios", {})
            company_data = fundamental_data.get("analysis", {}).get("company_data", {})
            financials["market_cap"] = (
                fundamental_data.get("market_cap", 0)
                or company_data.get("market_cap", 0)
                or ratios.get("market_cap", 0)
                or fundamental_data.get("analysis", {}).get("response", {}).get("market_cap", 0)
            )
            if financials["market_cap"] > 0:
                self.logger.info(f"✅ Backfilled market_cap from fundamental agent: ${financials['market_cap']:,.0f}")

        return financials

    def _backfill_scores(self, scores: dict, fundamental_data: dict) -> dict:
        """Backfill scores from fundamental data."""
        # If composite is still default, try to calculate from fundamentals
        if scores["composite"] == 50:
            quality_score = fundamental_data.get("data_quality", {}).get("data_quality_score", 0)
            if quality_score > 0:
                # Use quality score as a proxy for composite
                scores["composite"] = quality_score

        return scores

    def _backfill_from_technical(self, financials: dict, technical_data: dict) -> dict:
        """
        Backfill missing financials from technical analysis.

        Technical agent has current_price in: technical['analysis']['response']['current_price']
        """
        # Extract from technical analysis response
        tech_analysis = technical_data.get("analysis", {}).get("response", {})

        if financials["current_price"] == 0:
            current_price = tech_analysis.get("current_price", 0)
            if current_price > 0:
                financials["current_price"] = current_price
                self.logger.info(f"✅ Backfilled current_price from technical agent: ${current_price:.2f}")

        # Technical analysis might also have market_cap in some cases
        if financials["market_cap"] == 0:
            market_cap = tech_analysis.get("market_cap", 0)
            if market_cap > 0:
                financials["market_cap"] = market_cap
                self.logger.info(f"✅ Backfilled market_cap from technical agent: ${market_cap:,.0f}")

        return financials

    def _backfill_technical_indicators(self, payload: dict, technical_data: dict) -> dict:
        """
        Backfill technical indicator fields from technical analysis data.

        These fields are needed by PDFReportGenerator._create_technical_summary()
        and _create_entry_exit_section() to render technical analysis pages.

        Args:
            payload: The partially built payload dict to add indicators to
            technical_data: Raw technical analysis data from the technical agent

        Returns:
            Updated payload dict with technical indicator fields
        """
        if not technical_data or not isinstance(technical_data, dict):
            return payload

        # Extract from technical analysis response - handle nested structures
        tech_response = technical_data.get("analysis", {}).get("response", {})
        if not isinstance(tech_response, dict):
            tech_response = {}

        # Also check top-level and technical_indicators sub-dict
        tech_indicators = tech_response.get("technical_indicators", {})
        if not isinstance(tech_indicators, dict):
            tech_indicators = {}

        # --- Support levels ---
        if not payload.get("support_levels"):
            support = (
                tech_response.get("support_levels")
                or tech_indicators.get("support_levels")
                or technical_data.get("support_levels")
            )
            if support and isinstance(support, list) and len(support) > 0:
                payload["support_levels"] = support
                self.logger.info(f"✅ Backfilled support_levels from technical agent: {support[:3]}")

        # --- Resistance levels ---
        if not payload.get("resistance_levels"):
            resistance = (
                tech_response.get("resistance_levels")
                or tech_indicators.get("resistance_levels")
                or technical_data.get("resistance_levels")
            )
            if resistance and isinstance(resistance, list) and len(resistance) > 0:
                payload["resistance_levels"] = resistance
                self.logger.info(f"✅ Backfilled resistance_levels from technical agent: {resistance[:3]}")

        # --- Trend direction ---
        if not payload.get("trend_direction") or payload.get("trend_direction") == "NEUTRAL":
            trend = (
                tech_response.get("trend_direction")
                or tech_response.get("trend")
                or tech_indicators.get("trend_direction")
                or technical_data.get("trend_direction")
            )
            if trend and isinstance(trend, str) and trend.strip():
                payload["trend_direction"] = trend.strip().upper()
                self.logger.info(f"✅ Backfilled trend_direction from technical agent: {payload['trend_direction']}")

        # --- Momentum signals ---
        if not payload.get("momentum_signals"):
            signals = (
                tech_response.get("momentum_signals")
                or tech_response.get("signals")
                or tech_indicators.get("momentum_signals")
                or technical_data.get("momentum_signals")
            )
            if signals and isinstance(signals, list) and len(signals) > 0:
                payload["momentum_signals"] = signals[:5]
                self.logger.info(f"✅ Backfilled {len(signals[:5])} momentum_signals from technical agent")

        # --- Entry signals ---
        if not payload.get("entry_signals"):
            entry = tech_response.get("entry_signals") or technical_data.get("entry_signals")
            if entry and isinstance(entry, list) and len(entry) > 0:
                payload["entry_signals"] = entry[:5]
                self.logger.info(f"✅ Backfilled {len(entry[:5])} entry_signals from technical agent")

        # --- Exit signals ---
        if not payload.get("exit_signals"):
            exit_sigs = tech_response.get("exit_signals") or technical_data.get("exit_signals")
            if exit_sigs and isinstance(exit_sigs, list) and len(exit_sigs) > 0:
                payload["exit_signals"] = exit_sigs[:5]
                self.logger.info(f"✅ Backfilled {len(exit_sigs[:5])} exit_signals from technical agent")

        # --- Optimal entry zone ---
        if not payload.get("optimal_entry_zone"):
            zone = tech_response.get("optimal_entry_zone") or technical_data.get("optimal_entry_zone")
            if zone and isinstance(zone, dict):
                payload["optimal_entry_zone"] = zone
                self.logger.info("✅ Backfilled optimal_entry_zone from technical agent")

        return payload

    def _scale_score(self, score: float) -> float:
        """
        Convert score to 0-10 scale.

        Handles both 0-100 and 0-10 scale inputs intelligently:
        - If score > 10, assume 0-100 scale and divide by 10
        - If score <= 10, assume already on 0-10 scale
        """
        if score > 10:
            # Score is on 0-100 scale, convert to 0-10
            return round(float(score) / 10, 1)
        else:
            # Score is already on 0-10 scale
            return round(float(score), 1)

    def _validate_payload(self, symbol: str, financials: dict, scores: dict):
        """Validate critical fields and log warnings."""
        issues = []

        if financials["current_price"] == 0:
            issues.append("current_price=0")

        if financials["market_cap"] == 0:
            issues.append("market_cap=0")

        if scores["composite"] == 50:
            issues.append("composite_score=default(50)")

        if issues:
            self.logger.warning(f"⚠️  Payload validation issues for {symbol}: {', '.join(issues)}")
