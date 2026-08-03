from investigator.domain.services.rl.reward_calculator import (
    RewardCalculator,
    calculate_reward,
    get_reward_calculator,
)


def test_invalid_prices_return_neutral_reward_components():
    result = RewardCalculator().calculate(predicted_fv=0, price_at_prediction=100, actual_price=110)

    assert result.reward == 0.0
    assert result.predicted_direction == 0
    assert result.actual_direction == 0
    assert result.direction_correct is False


def test_long_prediction_rewards_correct_upside_direction():
    result = RewardCalculator().calculate(
        predicted_fv=125,
        price_at_prediction=100,
        actual_price=112,
        days=90,
        beta=1.2,
    )

    assert result.predicted_direction == 1
    assert result.actual_direction == 1
    assert result.direction_correct is True
    assert result.position_return > 0
    assert result.reward > 0


def test_short_prediction_rewards_correct_downside_direction():
    result = RewardCalculator().calculate(
        predicted_fv=75,
        price_at_prediction=100,
        actual_price=86,
        days=90,
        beta=1.1,
    )

    assert result.predicted_direction == -1
    assert result.actual_direction == -1
    assert result.direction_correct is True
    assert result.position_return > 0
    assert result.reward > 0


def test_wrong_short_prediction_applies_squeeze_penalty():
    calculator = RewardCalculator(short_wrong_base_multiplier=1.5, short_squeeze_sensitivity=2.0)

    result = calculator.calculate(predicted_fv=80, price_at_prediction=100, actual_price=130)

    assert result.predicted_direction == -1
    assert result.direction_correct is False
    assert result.direction_factor > calculator.short_wrong_base_multiplier
    assert result.reward < 0


def test_wrong_long_prediction_uses_recoverable_loss_dampening():
    calculator = RewardCalculator(long_wrong_dampening=0.7)

    result = calculator.calculate(predicted_fv=130, price_at_prediction=100, actual_price=85)

    assert result.predicted_direction == 1
    assert result.direction_correct is False
    assert result.direction_factor == calculator.long_wrong_dampening
    assert result.reward < 0


def test_total_loss_branch_caps_annualized_return():
    result = RewardCalculator().calculate(predicted_fv=50, price_at_prediction=100, actual_price=250)

    assert result.predicted_direction == -1
    assert result.position_return <= -1
    assert result.annualized_return == -10.0


def test_simple_and_per_model_reward_helpers_filter_invalid_fair_values():
    calculator = RewardCalculator()

    scalar = calculator.calculate_simple(125, 100, 112, days=90, beta=1.0)
    detailed = calculator.calculate(125, 100, 112, days=90, beta=1.0)
    per_model = calculator.calculate_per_model_rewards(
        {"dcf": 125.0, "pe": None, "ps": 0.0, "pb": 85.0},
        price_at_prediction=100,
        actual_price=112,
        days=90,
    )

    assert scalar == detailed.reward
    assert set(per_model) == {"dcf", "pb"}
    assert per_model["dcf"]["direction_correct"] is True
    assert per_model["pb"]["direction_correct"] is False


def test_singleton_and_convenience_function_return_usable_calculator():
    calculator = get_reward_calculator()

    assert calculator is get_reward_calculator()
    assert isinstance(calculate_reward(120, 100, 110), float)
