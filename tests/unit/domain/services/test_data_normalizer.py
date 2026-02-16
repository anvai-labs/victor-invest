from investigator.domain.services.data_normalizer import DataNormalizer


def test_round_financial_data_preserves_revenue_growth_guidance_precision() -> None:
    payload = {"revenue_growth_guidance": 0.04, "earnings_growth_guidance": 0.05555}

    rounded = DataNormalizer.round_financial_data(payload)

    assert rounded["revenue_growth_guidance"] == 0.04
    assert rounded["earnings_growth_guidance"] == 0.0556


def test_round_financial_data_keeps_revenue_as_whole_number() -> None:
    payload = {"revenue": 12345.67}

    rounded = DataNormalizer.round_financial_data(payload)

    assert rounded["revenue"] == 12346.0
