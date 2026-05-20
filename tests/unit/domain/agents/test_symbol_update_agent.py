from investigator.domain.agents.symbol_update import SymbolUpdateAgent


def test_extract_metrics_skips_suspicious_split_like_fair_values():
    agent = SymbolUpdateAgent("test_symbol_update")

    update_data = agent._extract_metrics(
        "NFLX",
        {
            "valuation": {"current_price": 87.02},
            "fair_value": 509.31,
            "multi_model_summary": {
                "blended_fair_value": 509.31,
                "model_agreement_score": 0.92,
                "models": [
                    {
                        "model": "pe",
                        "fair_value_per_share": 509.31,
                        "applicable": True,
                    }
                ],
            },
        },
        {},
    )

    assert "fair_value_blended" not in update_data
    assert "fair_value_pe" not in update_data
    assert "valuation_updated_at" not in update_data
    assert update_data["divergence_flag"] is True
    assert update_data["valuation_models_json"]["valuation_quality_flag"] == "split_or_stale_price_mismatch"


def test_extract_metrics_persists_reasonable_fair_values():
    agent = SymbolUpdateAgent("test_symbol_update")

    update_data = agent._extract_metrics(
        "AAPL",
        {
            "valuation": {"current_price": 190.0},
            "fair_value": 210.0,
            "multi_model_summary": {
                "blended_fair_value": 210.0,
                "model_agreement_score": 0.8,
                "models": [
                    {
                        "model": "pe",
                        "fair_value_per_share": 208.0,
                        "applicable": True,
                    }
                ],
            },
        },
        {},
    )

    assert update_data["fair_value_blended"] == 210.0
    assert update_data["fair_value_pe"] == 208.0
    assert "valuation_updated_at" in update_data
    assert "valuation_quality_flag" not in update_data["valuation_models_json"]
