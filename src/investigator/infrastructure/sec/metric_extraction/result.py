"""
Extraction Result Types

Provides structured result objects for metric extraction operations,
including value, metadata, and audit trail information.

SOLID Principle: Single Responsibility
- ExtractionResult: Holds extraction outcome
- ExtractionAudit: Holds extraction attempt history
"""

from dataclasses import dataclass, field
from enum import Enum


class MatchMethod(Enum):
    """How a period match was achieved."""

    BY_PERIOD_END = "by_period_end"  # Exact end date match (most reliable)
    BY_DATE_RANGE = "by_date_range"  # Start/end date range match
    BY_FRAME_FIELD = "by_frame_field"  # CY2024Q3 frame field match
    BY_ADSH_FY_FP = "by_adsh_fy_fp"  # Legacy ADSH + fy + fp match
    BY_ADSH_ONLY = "by_adsh_only"  # ADSH match without fy/fp filter
    DERIVED = "derived"  # Calculated from other metrics
    NOT_FOUND = "not_found"  # No match found


class ExtractionConfidence(Enum):
    """Confidence level in extracted value."""

    HIGH = "high"  # Exact match on all criteria
    MEDIUM = "medium"  # Partial match or fallback tag used
    LOW = "low"  # Multiple fallbacks or fuzzy match
    DERIVED = "derived"  # Value was calculated, not extracted
    NONE = "none"  # No value found


@dataclass
class ExtractionAttempt:
    """Record of a single extraction attempt."""

    strategy_name: str
    tag_name: str
    matched: bool
    entries_found: int
    selected_entry: dict | None = None
    reason: str | None = None
    duration_ms: float = 0.0


@dataclass
class ExtractionAudit:
    """
    Complete audit trail of extraction attempts.

    Provides full traceability of which strategies and tags were tried,
    enabling debugging and quality assessment.
    """

    canonical_key: str
    target_period_end: str | None = None
    target_fiscal_year: int | None = None
    target_fiscal_period: str | None = None
    target_adsh: str | None = None

    attempts: list[ExtractionAttempt] = field(default_factory=list)
    total_duration_ms: float = 0.0
    started_at: str | None = None
    completed_at: str | None = None

    def add_attempt(self, attempt: ExtractionAttempt) -> None:
        """Add an extraction attempt to the audit trail."""
        self.attempts.append(attempt)
        self.total_duration_ms += attempt.duration_ms

    def summary(self) -> str:
        """Generate human-readable summary."""
        successful = [a for a in self.attempts if a.matched]
        failed = [a for a in self.attempts if not a.matched]

        lines = [
            f"Extraction Audit: {self.canonical_key}",
            (
                f"  Target: period_end={self.target_period_end}, "
                f"fiscal={self.target_fiscal_year}-{self.target_fiscal_period}"
            ),
            f"  Attempts: {len(self.attempts)} ({len(successful)} succeeded, {len(failed)} failed)",
        ]

        if successful:
            first_success = successful[0]
            lines.append(f"  Matched via: {first_success.strategy_name} using tag '{first_success.tag_name}'")

        if failed and not successful:
            lines.append(f"  Failed strategies: {[a.strategy_name for a in failed]}")

        return "\n".join(lines)


@dataclass
class ExtractionResult:
    """
    Result of a metric extraction operation.

    Contains the extracted value along with comprehensive metadata
    about how it was obtained and confidence level.

    Attributes:
        success: Whether extraction succeeded
        value: The extracted value (None if not found)
        source_tag: XBRL tag used for extraction
        match_method: How the period was matched
        confidence: Confidence level in the result
        period_end: Period end date of extracted entry
        entry: Full SEC entry dict (for debugging)
        audit: Complete extraction audit trail
        error: Error message if extraction failed
    """

    success: bool
    value: float | None = None
    source_tag: str | None = None
    match_method: MatchMethod = MatchMethod.NOT_FOUND
    confidence: ExtractionConfidence = ExtractionConfidence.NONE

    # Metadata from matched entry
    period_end: str | None = None
    period_start: str | None = None
    duration_days: int | None = None
    form: str | None = None
    filed_date: str | None = None
    accn: str | None = None

    # SEC fields (may be unreliable)
    sec_fy: int | None = None
    sec_fp: str | None = None

    # Full entry and audit
    entry: dict | None = None
    audit: ExtractionAudit | None = None
    error: str | None = None

    @classmethod
    def not_found(
        cls,
        canonical_key: str,
        audit: ExtractionAudit | None = None,
        reason: str = "No matching entry found",
    ) -> "ExtractionResult":
        """Factory for failed extraction."""
        return cls(
            success=False,
            match_method=MatchMethod.NOT_FOUND,
            confidence=ExtractionConfidence.NONE,
            audit=audit,
            error=reason,
        )

    @classmethod
    def from_entry(
        cls,
        value: float,
        source_tag: str,
        entry: dict,
        match_method: MatchMethod,
        confidence: ExtractionConfidence = ExtractionConfidence.HIGH,
        audit: ExtractionAudit | None = None,
    ) -> "ExtractionResult":
        """Factory from SEC entry dict."""
        # Calculate duration
        duration_days = None
        start = entry.get("start")
        end = entry.get("end")
        if start and end:
            try:
                from datetime import datetime as dt

                start_date = dt.strptime(start, "%Y-%m-%d")
                end_date = dt.strptime(end, "%Y-%m-%d")
                duration_days = (end_date - start_date).days
            except ValueError:
                pass

        return cls(
            success=True,
            value=value,
            source_tag=source_tag,
            match_method=match_method,
            confidence=confidence,
            period_end=entry.get("end"),
            period_start=entry.get("start"),
            duration_days=duration_days,
            form=entry.get("form"),
            filed_date=entry.get("filed"),
            accn=entry.get("accn"),
            sec_fy=entry.get("fy"),
            sec_fp=entry.get("fp"),
            entry=entry,
            audit=audit,
        )

    @classmethod
    def derived(
        cls,
        value: float,
        formula: str,
        components: dict[str, float],
        audit: ExtractionAudit | None = None,
    ) -> "ExtractionResult":
        """Factory for derived/calculated values."""
        return cls(
            success=True,
            value=value,
            source_tag=f"derived:{formula}",
            match_method=MatchMethod.DERIVED,
            confidence=ExtractionConfidence.DERIVED,
            audit=audit,
        )

    def __repr__(self) -> str:
        if self.success:
            return (
                f"ExtractionResult(value={self.value:,.0f}, "
                f"tag='{self.source_tag}', "
                f"method={self.match_method.value}, "
                f"confidence={self.confidence.value})"
            )
        return f"ExtractionResult(success=False, error='{self.error}')"
