from investigator.domain.services.filing_guidance_extractor import (
    extract_forward_guidance,
    select_best_guidance,
)


def test_extract_forward_guidance_revenue_and_eps_ranges():
    text = """
    We are raising our full year 2026 revenue outlook to between $9.8 billion and $10.2 billion.
    Management also expects diluted EPS guidance of $6.20 to $6.60 for fiscal year 2026.
    """

    result = extract_forward_guidance(
        text=text,
        form_type="8-K",
        filing_date="2026-02-13",
    )

    assert result["source"] == "sec_filing_regex"
    assert result["source_form"] == "8-K"
    assert result["confidence_score"] > 0.5
    assert result["revenue_guidance"]["horizon"] == "1y"
    assert result["eps_guidance"]["horizon"] == "1y"
    assert result["revenue_guidance"]["mid"] > 9_900_000_000
    assert abs(result["eps_guidance"]["mid"] - 6.4) < 1e-6


def test_extract_forward_guidance_returns_empty_when_missing():
    result = extract_forward_guidance(
        text="The business remains focused on long-term execution.",
        form_type="10-Q",
        filing_date="2026-01-31",
    )
    assert result == {}


def test_extract_forward_guidance_ignores_year_pairs_masquerading_as_eps():
    text = """
    Our outlook discussion includes diluted EPS context for fiscal years 2024 and 2025,
    but does not provide an explicit EPS dollar range.
    """

    result = extract_forward_guidance(
        text=text,
        form_type="10-K",
        filing_date="2026-02-13",
    )

    assert "eps_guidance" not in result


def test_extract_forward_guidance_handles_inline_html_text():
    text = """
    <div>Management expects diluted EPS guidance of <b>$6.20</b> to <b>$6.60</b>
    for fiscal year 2026.</div>
    """
    result = extract_forward_guidance(
        text=text,
        form_type="8-K",
        filing_date="2026-02-13",
    )
    assert abs(result["eps_guidance"]["mid"] - 6.4) < 1e-6


def test_extract_forward_guidance_handles_expect_before_revenue_range():
    text = """
    We expect first quarter 2026 total revenue to be in the range of $53.5-56.5 billion.
    """
    result = extract_forward_guidance(
        text=text,
        form_type="8-K",
        filing_date="2026-01-28",
    )

    assert result["revenue_guidance"]["horizon"] == "1q"
    assert abs(result["revenue_guidance"]["low"] - 53_500_000_000.0) < 1.0
    assert abs(result["revenue_guidance"]["high"] - 56_500_000_000.0) < 1.0
    assert result["confidence_score"] >= 0.4


def test_extract_forward_guidance_ignores_historical_growth_without_forward_cue():
    text = "Revenue growth was 0% year over year in 2025."
    result = extract_forward_guidance(
        text=text,
        form_type="10-Q",
        filing_date="2026-02-13",
    )
    assert result == {}


def test_select_best_guidance_prefers_confident_candidate():
    candidates = [
        {
            "source_form": "10-Q",
            "confidence_score": 0.4,
            "revenue_guidance": {"mid": 100.0},
        },
        {
            "source_form": "8-K",
            "confidence_score": 0.75,
            "revenue_guidance": {"mid": 101.0},
            "eps_guidance": {"mid": 4.2},
        },
    ]

    best = select_best_guidance(candidates)
    assert best["source_form"] == "8-K"
    assert best["confidence_score"] == 0.75
