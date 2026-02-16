from investigator.domain.agents.fundamental.valuation_models import (
    _normalize_share_count,
    _resolve_guidance_overrides,
)


def test_resolve_guidance_overrides_from_ranges():
    guidance = {
        "source_form": "8-K",
        "confidence_score": 0.8,
        "revenue_guidance": {"low": 11_000_000_000, "high": 13_000_000_000, "horizon": "1y"},
        "eps_guidance": {"low": 2.4, "high": 2.6, "horizon": "1q"},
    }

    revenue_growth, earnings_growth, annualized_eps, metadata = _resolve_guidance_overrides(
        guidance_context=guidance,
        base_eps=8.0,
        base_revenue=10_000_000_000.0,
    )

    # Revenue guidance midpoint=12B vs base=10B => 20% implied growth
    assert abs((revenue_growth or 0.0) - 0.2) < 1e-6
    # EPS guidance midpoint=2.5 for 1q => annualized=10.0; vs base 8 => 25% growth
    assert abs((annualized_eps or 0.0) - 10.0) < 1e-6
    assert abs((earnings_growth or 0.0) - 0.25) < 1e-6
    assert metadata["guidance_source_form"] == "8-K"


def test_resolve_guidance_overrides_uses_direct_growth_when_available():
    guidance = {
        "source_form": "10-Q",
        "confidence_score": 0.6,
        "revenue_growth_guidance": 15.0,  # percent format
        "earnings_growth_guidance": 0.12,  # ratio format
    }

    revenue_growth, earnings_growth, annualized_eps, metadata = _resolve_guidance_overrides(
        guidance_context=guidance,
        base_eps=5.0,
        base_revenue=100.0,
    )

    assert abs((revenue_growth or 0.0) - 0.15) < 1e-6
    assert abs((earnings_growth or 0.0) - 0.12) < 1e-6
    assert annualized_eps is None
    assert metadata["guidance_source_form"] == "10-Q"


def test_resolve_guidance_overrides_rejects_implausible_eps_override():
    guidance = {
        "source_form": "10-K",
        "confidence_score": 0.35,
        "eps_guidance": {"low": 10.0, "high": 2024.0, "horizon": "1y"},
    }

    revenue_growth, earnings_growth, annualized_eps, metadata = _resolve_guidance_overrides(
        guidance_context=guidance,
        base_eps=12.0,
        base_revenue=100.0,
    )

    assert revenue_growth is None
    assert earnings_growth is None
    assert annualized_eps is None
    assert "guidance_eps_mid" not in metadata
    assert metadata.get("guidance_eps_rejected_reason", "").startswith("implausible_ratio_")


def test_normalize_share_count_scales_millions_encoded_values():
    assert _normalize_share_count(715.9) == 715_900_000.0
    assert _normalize_share_count(3_526_000_000) == 3_526_000_000.0
