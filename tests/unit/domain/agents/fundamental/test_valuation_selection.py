from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.valuation_selection import (
    calculate_enterprise_value,
    load_model_selection_rules,
    select_models_for_company,
)
from investigator.domain.services.valuation.models.company_profile import (
    CompanyArchetype,
    CompanyProfile,
    DataQualityFlag,
)


def test_calculate_enterprise_value_prefers_explicit_field():
    result = calculate_enterprise_value({"enterprise_value": "125.5"}, {"total_debt": 50, "cash": 10})

    assert result == 125.5


def test_calculate_enterprise_value_falls_back_to_market_cap_plus_debt_minus_cash():
    result = calculate_enterprise_value(
        {"market_cap": 200.0},
        {"total_debt": 40.0, "cash_and_equivalents": 15.0},
    )

    assert result == 225.0


def test_load_model_selection_rules_handles_missing_and_valid_file(tmp_path):
    logger = MagicMock()
    missing = load_model_selection_rules(tmp_path / "missing.yaml", logger=logger)

    rules_path = tmp_path / "model_selection.yaml"
    rules_path.write_text("defaults:\n  include: [dcf, pe]\n", encoding="utf-8")
    loaded = load_model_selection_rules(rules_path, logger=logger)

    assert missing == {}
    assert loaded == {"defaults": {"include": ["dcf", "pe"]}}


def test_select_models_for_company_applies_archetype_secondary_and_blocking_flags():
    profile = CompanyProfile(symbol="AAPL", sector="Technology")
    profile.primary_archetype = CompanyArchetype.HIGH_GROWTH
    profile.secondary_archetype = CompanyArchetype.CAPITAL_INTENSIVE
    profile.data_quality_flags = [DataQualityFlag.STALE_REFERENCE_DATA]

    rules = {
        "defaults": {
            "include": ["dcf"],
            "blocking_flags": {"STALE_REFERENCE_DATA": ["ev_ebitda"]},
            "min_models": 1,
        },
        "archetypes": {
            "high_growth": {
                "include": ["ps", "ev_ebitda"],
                "secondary": {
                    "capital_intensive": {
                        "include": ["pb"],
                    }
                },
            }
        },
    }

    result = select_models_for_company(profile, rules)

    assert set(result) == {"dcf", "ps", "pb"}


def test_select_models_for_company_returns_none_when_minimum_not_met():
    profile = CompanyProfile(symbol="AAPL", sector="Technology")
    rules = {"defaults": {"include": ["dcf"], "exclude": ["dcf"], "min_models": 1}}

    assert select_models_for_company(profile, rules) is None
