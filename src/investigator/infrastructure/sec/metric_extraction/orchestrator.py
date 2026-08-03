"""
Metric Extraction Orchestrator

Coordinates multi-level fallback chains for robust metric extraction:
1. Period Matcher Chain - Tries multiple matching strategies
2. Tag Fallback Chain - Tries sector-aware XBRL tags
3. Derived Value Chain - Calculates from other metrics if direct extraction fails

SOLID Principles:
- Single Responsibility: Coordinates extraction, delegates to strategies
- Dependency Inversion: Depends on abstract PeriodMatchStrategy
- Open/Closed: New strategies can be injected via configuration
"""

import logging
import time
from datetime import datetime
from typing import ClassVar

from .result import (
    ExtractionAttempt,
    ExtractionAudit,
    ExtractionConfidence,
    ExtractionResult,
)
from .strategies import (
    ByAdshFyFpMatcher,
    ByAdshOnlyMatcher,
    ByDateRangeMatcher,
    ByFrameFieldMatcher,
    ByPeriodEndMatcher,
    MatchContext,
    PeriodMatchStrategy,
)

logger = logging.getLogger(__name__)


class MetricExtractionOrchestrator:
    """
    Orchestrates metric extraction with multi-level fallback chains.

    Strategy Priority (executed in order until success):
    1. ByPeriodEndMatcher - Most reliable, matches by exact end date
    2. ByDateRangeMatcher - Handles off-by-one date differences
    3. ByFrameFieldMatcher - Uses calendar-based frame field
    4. ByAdshOnlyMatcher - Uses ADSH with duration filtering
    5. ByAdshFyFpMatcher - Legacy, least reliable (fy field can be wrong)

    For each matching strategy, tries all XBRL tags in the fallback chain
    (sector-specific first, then global fallback).

    Usage:
        orchestrator = MetricExtractionOrchestrator(
            sector='Technology',
            industry='Electronic Components',
            canonical_mapper=get_canonical_mapper()
        )

        result = orchestrator.extract(
            canonical_key='total_revenue',
            us_gaap=company_facts['facts']['us-gaap'],
            target_period_end='2025-06-27',
            target_fiscal_period='FY'
        )

        if result.success:
            print(f"Revenue: {result.value:,.0f}")
        else:
            print(f"Extraction failed: {result.error}")
    """

    # Default matcher chain (ordered by reliability)
    DEFAULT_MATCHERS: ClassVar[list] = [
        ByPeriodEndMatcher(),
        ByDateRangeMatcher(),
        ByFrameFieldMatcher(),
        ByAdshOnlyMatcher(),
        ByAdshFyFpMatcher(),
    ]

    # Metrics that are frequently absent in valid filings and should not flood WARNING logs.
    LOW_SIGNAL_MISSING_KEYS: ClassVar[set] = {
        "operating_expenses",
        "interest_expense",
        "earnings_per_share_diluted",
        "intangible_assets",
        "deferred_revenue",
        "treasury_stock",
        "preferred_stock_dividends",
        "common_stock_dividends",
        "financial_total_deposits",
        "financial_repo_borrowings",
        "financial_fhlb_borrowings",
        "financial_other_short_term_borrowings",
    }
    HISTORICAL_OPTIONAL_WARNING_KEYS: ClassVar[set] = {
        "short_term_debt",
        "goodwill",
        "dividends_paid",
        "other_comprehensive_income",
    }
    HISTORICAL_WARNING_CUTOFF_YEARS = 8
    MAX_WARNING_FAILURES_PER_KEY = 3

    def __init__(
        self,
        sector: str | None = None,
        industry: str | None = None,
        canonical_mapper=None,
        matchers: list[PeriodMatchStrategy] | None = None,
        enable_audit: bool = True,
    ):
        """
        Initialize the orchestrator.

        Args:
            sector: Company sector for sector-specific tag resolution
            industry: Company industry for industry-specific tag resolution
            canonical_mapper: CanonicalKeyMapper instance (if None, will import)
            matchers: Custom matcher chain (if None, uses DEFAULT_MATCHERS)
            enable_audit: Whether to build detailed audit trails
        """
        self.sector = sector
        self.industry = industry
        self.matchers = matchers or self.DEFAULT_MATCHERS
        self.enable_audit = enable_audit

        # Initialize canonical mapper
        if canonical_mapper is None:
            from investigator.infrastructure.sec.canonical_mapper import (
                get_canonical_mapper,
            )

            self.canonical_mapper = get_canonical_mapper()
        else:
            self.canonical_mapper = canonical_mapper

        # Statistics
        self.stats = {
            "extractions": 0,
            "successes": 0,
            "by_strategy": {},
            "by_tag_position": {},
        }
        self._failure_log_counts: dict[str, int] = {}
        self._failure_log_keys = set()

    def extract(
        self,
        canonical_key: str,
        us_gaap: dict,
        target_period_end: str | None = None,
        target_fiscal_year: int | None = None,
        target_fiscal_period: str | None = None,
        target_adsh: str | None = None,
        fiscal_year_end: str | None = None,
        tolerance_days: int = 7,
    ) -> ExtractionResult:
        """
        Extract a metric using multi-level fallback chains.

        Args:
            canonical_key: Canonical metric key (e.g., 'total_revenue')
            us_gaap: SEC us-gaap JSON structure
            target_period_end: Target period end date (YYYY-MM-DD) - MOST IMPORTANT
            target_fiscal_year: Target fiscal year (unreliable in SEC data)
            target_fiscal_period: Target fiscal period (FY, Q1, Q2, Q3, Q4)
            target_adsh: Target accession number
            fiscal_year_end: Company's fiscal year end (e.g., '-06-27')
            tolerance_days: Days tolerance for date range matching

        Returns:
            ExtractionResult with value, metadata, and audit trail
        """
        start_time = time.time()
        self.stats["extractions"] += 1

        # Create audit trail
        audit = (
            ExtractionAudit(
                canonical_key=canonical_key,
                target_period_end=target_period_end,
                target_fiscal_year=target_fiscal_year,
                target_fiscal_period=target_fiscal_period,
                target_adsh=target_adsh,
                started_at=datetime.now().isoformat(),
            )
            if self.enable_audit
            else None
        )

        # Create match context
        context = MatchContext(
            target_period_end=target_period_end,
            target_fiscal_year=target_fiscal_year,
            target_fiscal_period=target_fiscal_period,
            target_adsh=target_adsh,
            fiscal_year_end=fiscal_year_end,
            tolerance_days=tolerance_days,
        )

        # Get tag fallback chain for this canonical key
        fallback_tags = self.canonical_mapper.get_tags(canonical_key, sector=self.sector, industry=self.industry)

        if not fallback_tags:
            if self._is_low_signal_missing_metric(canonical_key):
                logger.debug(
                    "No XBRL tags found for low-signal canonical key '%s'",
                    canonical_key,
                )
            else:
                logger.warning(f"No XBRL tags found for canonical key '{canonical_key}'")
            if audit:
                audit.completed_at = datetime.now().isoformat()
            return ExtractionResult.not_found(
                canonical_key,
                audit=audit,
                reason=f"No XBRL tags configured for '{canonical_key}'",
            )

        # Try each matcher strategy
        for matcher in self.matchers:
            # For each matcher, try each tag in the fallback chain
            for tag_position, tag_name in enumerate(fallback_tags):
                attempt_start = time.time()

                # Get entries for this tag
                if tag_name not in us_gaap:
                    if audit:
                        audit.add_attempt(
                            ExtractionAttempt(
                                strategy_name=matcher.name,
                                tag_name=tag_name,
                                matched=False,
                                entries_found=0,
                                reason=f"Tag '{tag_name}' not in us_gaap",
                                duration_ms=(time.time() - attempt_start) * 1000,
                            )
                        )
                    continue

                tag_data = us_gaap[tag_name]
                units = tag_data.get("units", {})

                # Get expected unit (usually USD)
                mapping = self.canonical_mapper.mappings.get(canonical_key, {})
                expected_unit = mapping.get("unit", "USD")
                entries = units.get(expected_unit, [])

                if not entries:
                    if audit:
                        audit.add_attempt(
                            ExtractionAttempt(
                                strategy_name=matcher.name,
                                tag_name=tag_name,
                                matched=False,
                                entries_found=0,
                                reason=f"No {expected_unit} entries for tag",
                                duration_ms=(time.time() - attempt_start) * 1000,
                            )
                        )
                    continue

                # Try this matcher with this tag
                match_result = matcher.match(entries, context)

                if audit:
                    audit.add_attempt(
                        ExtractionAttempt(
                            strategy_name=matcher.name,
                            tag_name=tag_name,
                            matched=match_result.matched,
                            entries_found=len(match_result.entries),
                            selected_entry=match_result.entries[0] if match_result.entries else None,
                            reason=match_result.reason,
                            duration_ms=(time.time() - attempt_start) * 1000,
                        )
                    )

                if match_result.matched and match_result.entries:
                    # Select best entry (prefer individual quarter over YTD)
                    best_entry = self._select_best_entry(match_result.entries, target_fiscal_period)

                    if best_entry and best_entry.get("val") is not None:
                        value = best_entry["val"]

                        # Determine confidence based on strategy and tag position
                        confidence = self._determine_confidence(matcher, tag_position, len(fallback_tags))

                        # Update statistics
                        self.stats["successes"] += 1
                        self.stats["by_strategy"][matcher.name] = self.stats["by_strategy"].get(matcher.name, 0) + 1
                        self.stats["by_tag_position"][tag_position] = (
                            self.stats["by_tag_position"].get(tag_position, 0) + 1
                        )

                        if audit:
                            audit.completed_at = datetime.now().isoformat()

                        logger.debug(
                            f"✓ Extracted {canonical_key} = {value:,.0f} "
                            f"via {matcher.name} using tag '{tag_name}' "
                            f"(position {tag_position + 1}/{len(fallback_tags)})"
                        )

                        return ExtractionResult.from_entry(
                            value=value,
                            source_tag=tag_name,
                            entry=best_entry,
                            match_method=match_result.method,
                            confidence=confidence,
                            audit=audit,
                        )

        # All strategies exhausted - try derived value calculation
        derived_result = self._try_derived_value(canonical_key, us_gaap, context, audit)
        if derived_result and derived_result.success:
            if audit:
                audit.completed_at = datetime.now().isoformat()
            return derived_result

        # Complete failure
        if audit:
            audit.completed_at = datetime.now().isoformat()

        elapsed_ms = (time.time() - start_time) * 1000
        failure_msg = (
            f"✗ Failed to extract {canonical_key} for period_end={target_period_end} "
            f"after trying {len(self.matchers)} strategies × {len(fallback_tags)} tags "
            f"({elapsed_ms:.1f}ms)"
        )
        failure_key = (
            canonical_key,
            target_period_end,
            target_fiscal_period,
            target_adsh,
        )
        self._log_extraction_failure(canonical_key, failure_key, failure_msg, target_period_end)

        return ExtractionResult.not_found(
            canonical_key,
            audit=audit,
            reason=f"Exhausted {len(self.matchers)} matchers × {len(fallback_tags)} tags",
        )

    def _log_extraction_failure(
        self,
        canonical_key: str,
        failure_key: tuple,
        failure_msg: str,
        target_period_end: str | None,
    ) -> None:
        """Log extraction failures with duplicate suppression and warning throttling."""
        if self._is_historical_optional_gap(canonical_key, target_period_end):
            logger.debug(
                "%s [historical optional metric warning downgraded to DEBUG]",
                failure_msg,
            )
            return

        if self._is_low_signal_missing_metric(canonical_key):
            logger.debug(failure_msg)
            return

        # Avoid repeating identical warnings for duplicate filings/period rows.
        if failure_key in self._failure_log_keys:
            logger.debug("%s [duplicate failure suppressed at WARNING level]", failure_msg)
            return
        self._failure_log_keys.add(failure_key)

        count = self._failure_log_counts.get(canonical_key, 0) + 1
        self._failure_log_counts[canonical_key] = count

        if count <= self.MAX_WARNING_FAILURES_PER_KEY:
            logger.warning(failure_msg)
            if count == self.MAX_WARNING_FAILURES_PER_KEY:
                logger.warning(
                    "Further '%s' extraction failures in this run will be downgraded to DEBUG",
                    canonical_key,
                )
            return

        logger.debug(
            "%s [warning-throttled: %s failures logged for key='%s']",
            failure_msg,
            count,
            canonical_key,
        )

    def _is_historical_optional_gap(self, canonical_key: str, target_period_end: str | None) -> bool:
        """Downgrade optional-metric misses for very old history to DEBUG."""
        if canonical_key not in self.HISTORICAL_OPTIONAL_WARNING_KEYS:
            return False
        if not target_period_end:
            return False

        try:
            period_end = datetime.strptime(target_period_end, "%Y-%m-%d")
        except ValueError:
            return False

        age_days = (datetime.utcnow() - period_end).days
        return age_days >= self.HISTORICAL_WARNING_CUTOFF_YEARS * 365

    def _get_expected_month_for_quarter(self, fiscal_period: str | None) -> int | None:
        """
        Get the expected month for a fiscal quarter based on period_end_date.

        For calendar year companies (most common):
        Q1 → March (month=3)
        Q2 → June (month=6)
        Q3 → September (month=9)
        Q4 → December (month=12)

        Note: For companies with non-calendar fiscal years (e.g., AAPL Sep, MSFT Jun),
        this mapping may differ. However, for SEC data matching, we can use the
        period_end_date month as a validation signal.

        Args:
            fiscal_period: Q1, Q2, Q3, Q4, or FY

        Returns:
            Expected month number (1-12) or None for FY
        """
        quarter_month_map = {
            "Q1": 3,  # March
            "Q2": 6,  # June
            "Q3": 9,  # September
            "Q4": 12,  # December
        }
        return quarter_month_map.get(fiscal_period)

    def _validate_quarter_by_period_end(self, entry: dict, target_fiscal_period: str) -> bool:
        """
        Validate that an entry's period_end_date matches the expected quarter.

        This is critical because the SEC API has multiple competing entries:
        - Individual quarters (Q1, Q2, Q3, Q4 data)
        - YTD (year-to-date cumulative data)
        - Comparative (prior year data)

        The frame field is often WRONG because it's set based on which entry
        was selected. Instead, we use period_end_date month to validate.

        Args:
            entry: SEC entry with 'end' field (period_end_date)
            target_fiscal_period: Target quarter (Q1, Q2, Q3, Q4)

        Returns:
            True if entry's period_end_date month matches expected quarter
        """
        expected_month = self._get_expected_month_for_quarter(target_fiscal_period)
        if expected_month is None:
            return True  # No validation for FY

        end = entry.get("end")
        if not end:
            return False

        try:
            end_date = datetime.strptime(end, "%Y-%m-%d")
            actual_month = end_date.month

            # Allow ±1 month tolerance for fiscal year variations
            # (e.g., companies with Sep, Jun, or other fiscal year ends)
            # For calendar companies, this should be exact match
            month_diff = abs(actual_month - expected_month)
            if month_diff <= 1:
                return True
            # Handle year wraparound (Dec vs Jan)
            return month_diff >= 11
        except ValueError:
            return False

    def _select_best_entry(self, entries: list[dict], target_fiscal_period: str | None) -> dict | None:
        """
        Select best entry from matched entries with multi-layer preference.

        Selection Priority:
        1. Period end date validation: For quarters, period_end month must match expected quarter
        2. Duration matching: Individual quarter (<120 days) over YTD
        3. Value anomaly detection: Warn if value >2x median of other entries
        4. Most recent filed date

        CRITICAL: The 'frame' field is often WRONG in SEC data because it's set
        based on which entry was selected. We CANNOT rely on it for quarter
        identification. Instead, we use period_end_date month to validate.

        Args:
            entries: List of matched SEC entries
            target_fiscal_period: Target fiscal period (FY, Q1, Q2, Q3, Q4)

        Returns:
            Best entry or None
        """
        if not entries:
            return None

        if len(entries) == 1:
            return entries[0]

        # Log duplicate value detection
        self._log_duplicate_values(entries, target_fiscal_period)

        # Categorize by duration (don't filter by frame - it's often wrong)
        individual = []
        ytd = []
        annual = []
        unknown = []

        for entry in entries:
            if entry.get("val") is None:
                continue

            start = entry.get("start")
            end = entry.get("end")

            if not start or not end:
                unknown.append(entry)
                continue

            try:
                start_date = datetime.strptime(start, "%Y-%m-%d")
                end_date = datetime.strptime(end, "%Y-%m-%d")
                days = (end_date - start_date).days

                if days < 120:
                    individual.append((entry, days))
                elif days < 270:
                    ytd.append((entry, days))
                else:
                    annual.append((entry, days))
            except ValueError:
                unknown.append(entry)

        # Select based on target fiscal period
        if target_fiscal_period == "FY":
            # For FY, prefer annual entries
            if annual:
                annual.sort(key=lambda x: x[0].get("filed", ""), reverse=True)
                return annual[0][0]
            if ytd:
                ytd.sort(key=lambda x: x[1], reverse=True)  # Prefer longer duration
                return ytd[-1][0]
        else:
            # ===================================================================
            # QUARTER SELECTION WITH PERIOD_END_DATE VALIDATION
            # ===================================================================
            #
            # Problem: SEC API returns multiple competing entries for same period:
            #   - Individual quarters (Q1, Q2, Q3, Q4) - ~90 days, actual quarter data
            #   - YTD (year-to-date) - ~180-270 days, cumulative data through period
            #   - Comparative - prior year data included for comparison
            #
            # Example: For Q1 2024, API might return:
            #   - Entry 1: Q1 2024 data (Mar 31 end, 90 days) ✓ CORRECT
            #   - Entry 2: Q4 2023 data (Dec 31 end, 90 days) ✗ COMPARATIVE
            #   - Entry 3: YTD data through Mar 31 (Jan 1-Mar 31, 90 days) ✗ YTD
            #
            # Solution: Validate period_end_date month matches expected quarter:
            #   - Q1 should end in March (month=3)
            #   - Q2 should end in June (month=6)
            #   - Q3 should end in September (month=9)
            #   - Q4 should end in December (month=12)
            #   - Allow ±1 month tolerance for non-calendar fiscal years
            #
            # This ensures we select the actual quarter data, not comparative/YTD.
            # ===================================================================
            if individual:
                # Step 1: Filter to entries where period_end_date matches expected quarter
                # Example: For Q2, only keep entries ending in June (month=6 ±1)
                validated_quarters = [
                    (entry, days)
                    for entry, days in individual
                    if self._validate_quarter_by_period_end(entry, target_fiscal_period)
                ]

                if validated_quarters:
                    # Step 2: Use validated entries (period_end_date matches expected quarter)
                    # Sort by filed date to get most recent filing
                    validated_quarters.sort(key=lambda x: x[0].get("filed", ""), reverse=True)
                    best = validated_quarters[0][0]
                    self._check_value_anomaly(best, validated_quarters, target_fiscal_period)
                    return best

                # Step 3: Fallback to any individual entry (better than YTD)
                # This handles edge cases where validation fails but entry is still usable
                individual.sort(key=lambda x: x[0].get("filed", ""), reverse=True)
                best = individual[0][0]
                self._check_value_anomaly(best, individual, target_fiscal_period)
                return best

            if ytd:
                # For YTD, prefer the most recent filed
                ytd.sort(key=lambda x: x[0].get("filed", ""), reverse=True)
                return ytd[0][0]

        # Fallback to any entry with value
        if unknown:
            unknown.sort(key=lambda x: x.get("filed", ""), reverse=True)
            return unknown[0]

        return entries[0] if entries else None

    def _log_duplicate_values(self, entries: list[dict], target_fiscal_period: str | None) -> None:
        """
        Log warning when multiple competing values exist for the same period.

        This helps identify cases where:
        - Discontinued operations inflate net income
        - Multiple XBRL tags report different values
        - YTD vs individual quarter ambiguity
        """
        if len(entries) < 2:
            return

        # Get all values
        values = [(e.get("val", 0), e) for e in entries if e.get("val") is not None]

        if len(values) < 2:
            return

        # Sort by value
        values.sort(key=lambda x: x[0])
        min_val = values[0][0]
        max_val = values[-1][0]

        # Check for significant variance (>50% difference)
        if min_val > 0 and max_val / min_val > 1.5:
            value_strs = [f"${v:,.0f}" for v, _ in values]
            frames = [(e.get("frame", "N/A"), e.get("fp", "N/A")) for _, e in values]

            logger.warning(
                f"Multiple competing values found for period_end="
                f"{entries[0].get('end', 'N/A')} (fp={target_fiscal_period}): "
                f"{value_strs} with frames/fp={frames} - "
                f"Values vary by {max_val / min_val:.1f}x (may include discontinued operations)"
            )

    def _check_value_anomaly(
        self,
        best_entry: dict,
        entries_with_days: list[tuple],
        target_fiscal_period: str | None,
    ) -> None:
        """
        Check if selected value is anomalous (>2x median) compared to other entries.

        This helps detect cases where one-time items (spin-offs, gains) inflate net income.
        """
        if len(entries_with_days) < 2:
            return

        values = [e[0].get("val", 0) for e in entries_with_days if e[0].get("val") is not None]

        if len(values) < 2:
            return

        import statistics

        median_val = statistics.median(values)
        selected_val = best_entry.get("val", 0)

        # Flag values >2x median as potential anomalies
        if selected_val > median_val * 2:
            logger.warning(
                f"Potential anomaly detected: Selected value ${selected_val:,.0f} is "
                f">{selected_val / median_val:.1f}x median ${median_val:,.0f} "
                f"(may include discontinued operations/one-time items like spin-offs) - "
                f"frame={best_entry.get('frame', 'N/A')}, fp={target_fiscal_period}"
            )

    def _is_low_signal_missing_metric(self, canonical_key: str) -> bool:
        """Return True when missing metric is usually non-actionable noise."""
        if canonical_key in self.LOW_SIGNAL_MISSING_KEYS:
            return True

        mapping = self.canonical_mapper.mappings.get(canonical_key, {})
        description = str(mapping.get("description", "")).lower()
        # Mapping files mark some keys as "support metric" (especially financial institution fields).
        return "support metric" in description

    def _determine_confidence(
        self, matcher: PeriodMatchStrategy, tag_position: int, total_tags: int
    ) -> ExtractionConfidence:
        """
        Determine extraction confidence based on how value was obtained.

        High confidence:
        - ByPeriodEndMatcher with first tag (position 0)

        Medium confidence:
        - ByPeriodEndMatcher with fallback tag
        - ByDateRangeMatcher with any tag

        Low confidence:
        - ByAdshFyFpMatcher (unreliable fy field)
        - Deep fallback tags (position > 2)
        """
        # Strategy-based confidence
        high_confidence_matchers = ["ByPeriodEndMatcher"]
        medium_confidence_matchers = [
            "ByDateRangeMatcher",
            "ByFrameFieldMatcher",
            "ByAdshOnlyMatcher",
        ]
        # ByAdshFyFpMatcher is low confidence

        if matcher.name in high_confidence_matchers:
            if tag_position == 0:
                return ExtractionConfidence.HIGH
            elif tag_position <= 2:
                return ExtractionConfidence.MEDIUM
            else:
                return ExtractionConfidence.LOW
        elif matcher.name in medium_confidence_matchers:
            if tag_position <= 1:
                return ExtractionConfidence.MEDIUM
            else:
                return ExtractionConfidence.LOW
        else:
            return ExtractionConfidence.LOW

    def _try_derived_value(
        self,
        canonical_key: str,
        us_gaap: dict,
        context: MatchContext,
        audit: ExtractionAudit | None,
    ) -> ExtractionResult | None:
        """
        Try to calculate derived value from other metrics.

        Example: free_cash_flow = operating_cash_flow - capital_expenditures
        """
        mapping = self.canonical_mapper.mappings.get(canonical_key, {})
        derived_config = mapping.get("derived", {})

        if not derived_config.get("enabled", False):
            return None

        formula = derived_config.get("formula")
        if not formula:
            return None

        # Get required fields
        required_fields = derived_config.get("required_fields", [])
        if not required_fields:
            return None

        # Extract required field values
        components = {}
        for field_key in required_fields:
            # Recursively extract (but don't allow derived to prevent loops)
            field_result = self.extract(
                canonical_key=field_key,
                us_gaap=us_gaap,
                target_period_end=context.target_period_end,
                target_fiscal_year=context.target_fiscal_year,
                target_fiscal_period=context.target_fiscal_period,
                target_adsh=context.target_adsh,
            )

            if field_result.success and field_result.value is not None:
                components[field_key] = field_result.value
            else:
                # Missing required component
                return None

        # Evaluate formula
        try:
            # Simple formula evaluation (supports +, -, *, /)
            value = self._evaluate_formula(formula, components)
            if value is not None:
                logger.debug(f"✓ Derived {canonical_key} = {value:,.0f} from formula '{formula}'")
                return ExtractionResult.derived(value=value, formula=formula, components=components, audit=audit)
        except Exception as e:
            logger.warning(f"Failed to evaluate formula '{formula}': {e}")

        return None

    def _evaluate_formula(self, formula: str, components: dict[str, float]) -> float | None:
        """
        Safely evaluate a simple arithmetic formula.

        Supports: +, -, *, /, variable names
        """
        # Replace variable names with values
        expr = formula
        for name, value in components.items():
            expr = expr.replace(name, str(value))

        # Only allow safe characters
        allowed = set("0123456789.+-*/()")
        if not all(c in allowed or c.isspace() for c in expr):
            logger.warning(f"Formula contains unsafe characters: {formula}")
            return None

        try:
            result = eval(expr)  # Safe because we validated characters
            return float(result)
        except Exception:
            return None

    def get_stats(self) -> dict:
        """Get extraction statistics."""
        success_rate = self.stats["successes"] / self.stats["extractions"] * 100 if self.stats["extractions"] > 0 else 0
        return {**self.stats, "success_rate": f"{success_rate:.1f}%"}
