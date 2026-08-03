from datetime import date

from investigator.domain.services.rl.models import (
    ABTestResults,
    CompanySize,
    GrowthStage,
    HoldingPeriod,
    RewardSignal,
    ValuationContext,
)


def test_context_to_dict_and_from_dict_preserve_rl_feature_fields():
    context = ValuationContext(
        symbol="NVDA",
        analysis_date=date(2026, 5, 20),
        sector="Information Technology",
        industry="Semiconductors",
        growth_stage=GrowthStage.HIGH_GROWTH,
        company_size=CompanySize.MEGA_CAP,
        profitability_score=0.91,
        current_price=950.0,
        optimal_holding_period="6m",
        optimal_holding_reward=0.72,
        ggm_applicable=False,
    )

    restored = ValuationContext.from_dict(context.to_dict())

    assert restored == context
    assert ValuationContext.from_dict({"symbol": "MSFT"}).analysis_date == date.today()


def test_reward_signal_best_holding_period_prefers_highest_non_null_reward():
    empty = RewardSignal(optimal_period="3m", optimal_reward=0.2)
    populated = RewardSignal(multi_period_rewards={"1m": 0.1, "3m": None, "6m": 0.55, "12m": 0.4})

    assert empty.primary_reward is None
    assert empty.get_best_holding_period() == ("3m", 0.2)
    assert RewardSignal(reward_30d=0.1, reward_90d=0.4).primary_reward == 0.4
    assert RewardSignal(reward_30d=0.1).primary_reward == 0.1
    assert populated.get_best_holding_period() == ("6m", 0.55)
    assert RewardSignal(multi_period_rewards={"1m": None}).get_best_holding_period() == (None, None)


def test_holding_period_from_days_uses_tolerance_thresholds():
    assert HoldingPeriod.from_days(30) == HoldingPeriod.ONE_MONTH
    assert HoldingPeriod.from_days(100) == HoldingPeriod.THREE_MONTHS
    assert HoldingPeriod.from_days(500) == HoldingPeriod.EIGHTEEN_MONTHS
    assert HoldingPeriod.from_days(2_000) == HoldingPeriod.THREE_YEARS
    assert HoldingPeriod.SIX_MONTHS.days == 180


def test_ab_test_recommendation_branches():
    base_kwargs = {
        "test_start_date": date(2026, 1, 1),
        "test_end_date": date(2026, 5, 1),
        "num_baseline_samples": 200,
        "rl_mean_reward": 0.4,
        "rl_mape": 0.12,
        "rl_direction_accuracy": 0.62,
        "baseline_mean_reward": 0.2,
        "baseline_mape": 0.15,
        "baseline_direction_accuracy": 0.55,
        "reward_p_value": 0.01,
        "mape_p_value": 0.05,
        "direction_p_value": 0.05,
        "mape_effect_size": 0.3,
    }

    not_significant = {**base_kwargs, "reward_p_value": 0.4}

    assert ABTestResults(num_rl_samples=50, reward_effect_size=0.8, **not_significant).recommendation == "CONTINUE_TEST"
    assert (
        ABTestResults(num_rl_samples=150, reward_effect_size=0.8, **not_significant).recommendation == "KEEP_BASELINE"
    )
    assert ABTestResults(num_rl_samples=150, reward_effect_size=0.1, **base_kwargs).recommendation == "CONTINUE_TEST"
    assert ABTestResults(num_rl_samples=150, reward_effect_size=0.3, **base_kwargs).recommendation == "GRADUAL_ROLLOUT"
    assert ABTestResults(num_rl_samples=150, reward_effect_size=0.8, **base_kwargs).recommendation == "FULL_ROLLOUT"
