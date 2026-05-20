from datetime import date, timedelta

from investigator.domain.services.rl.models import Experience, RewardSignal, ValuationContext
from investigator.domain.services.rl.training.experience_collector import ExperienceCollector


class _Tracker:
    def __init__(self, experiences):
        self.experiences = experiences
        self.calls = []

    def get_training_experiences(self, limit=10000, exclude_used=False):
        self.calls.append((limit, exclude_used))
        return self.experiences[:limit]


def _experience(idx, sector="Technology", tier="tier_1", days_old=120, reward=0.4):
    analysis_date = date.today() - timedelta(days=days_old)
    return Experience(
        id=idx,
        symbol=f"SYM{idx}",
        analysis_date=analysis_date,
        context=ValuationContext(
            symbol=f"SYM{idx}",
            analysis_date=analysis_date,
            sector=sector,
            industry="Software",
        ),
        weights_used={"dcf": 60.0, "pe": 40.0},
        tier_classification=tier,
        blended_fair_value=120.0,
        current_price=100.0,
        reward=RewardSignal(reward_90d=reward),
    )


def _collector(experiences):
    return ExperienceCollector(outcome_tracker=_Tracker(experiences), dao=object())


def test_collect_experiences_applies_age_reward_sector_and_tier_filters():
    experiences = [
        _experience(1, "Technology", "tier_1", days_old=150, reward=0.6),
        _experience(2, "Technology", "tier_2", days_old=150, reward=0.2),
        _experience(3, "Financials", "tier_1", days_old=150, reward=0.8),
        _experience(4, "Technology", "tier_1", days_old=10, reward=0.9),
    ]
    collector = _collector(experiences)

    result = collector.collect_experiences(
        min_days_ago=90,
        max_experiences=3,
        exclude_used=True,
        min_reward=0.5,
        sectors=["Technology"],
        tiers=["tier_1"],
    )

    assert [exp.id for exp in result] == [1]
    assert collector.outcome_tracker.calls == [(3, True)]


def test_collect_by_sector_limits_and_filters_minimum_group_size():
    experiences = [
        _experience(1, "Technology"),
        _experience(2, "Technology"),
        _experience(3, "Technology"),
        _experience(4, "Financials"),
    ]
    collector = _collector(experiences)

    grouped = collector.collect_by_sector(min_per_sector=2, max_per_sector=2)

    assert set(grouped) == {"Technology"}
    assert [exp.id for exp in grouped["Technology"]] == [1, 2]


def test_collect_recent_uses_cutoff_without_reward_age_filter():
    experiences = [
        _experience(1, days_old=5),
        _experience(2, days_old=35),
        _experience(3, days_old=15),
    ]
    collector = _collector(experiences)

    recent = collector.collect_recent(days=30, max_experiences=10)

    assert [exp.id for exp in recent] == [1, 3]


def test_split_methods_are_deterministic_and_preserve_counts():
    experiences = [_experience(i, sector="Technology" if i % 2 else "Financials") for i in range(10)]
    collector = _collector(experiences)

    train, val, test = collector.train_val_test_split(
        experiences,
        train_ratio=0.6,
        val_ratio=0.2,
        random_seed=7,
    )
    strat_train, strat_val, strat_test = collector.stratified_split(
        experiences,
        stratify_by="sector",
        train_ratio=0.5,
        val_ratio=0.25,
        random_seed=7,
    )

    assert (len(train), len(val), len(test)) == (6, 2, 2)
    assert len({exp.id for exp in train + val + test}) == 10
    assert len(strat_train) + len(strat_val) + len(strat_test) == 10
    assert {exp.context.sector for exp in strat_train}


def test_sample_balanced_handles_sector_tier_and_default_grouping():
    experiences = [
        _experience(1, "Technology", "tier_1"),
        _experience(2, "Technology", "tier_2"),
        _experience(3, "Financials", "tier_1"),
        _experience(4, "Financials", "tier_2"),
        _experience(5, "Health Care", "tier_1"),
    ]
    collector = _collector(experiences)

    by_sector = collector.sample_balanced(experiences, n_samples=4, balance_by="sector")
    by_tier = collector.sample_balanced(experiences, n_samples=4, balance_by="tier")
    default = collector.sample_balanced(experiences, n_samples=3, balance_by="unknown")

    assert len(by_sector) == 4
    assert len(by_tier) == 4
    assert len(default) == 3
    assert {exp.context.sector for exp in by_sector} >= {"Technology", "Financials", "Health Care"}


def test_statistics_reports_empty_and_populated_experience_sets():
    experiences = [
        _experience(1, "Technology", "tier_1", days_old=150, reward=0.6),
        _experience(2, "Financials", "tier_2", days_old=90, reward=-0.2),
    ]
    collector = _collector(experiences)

    empty = collector.get_statistics([])
    stats = collector.get_statistics(experiences)

    assert empty == {"count": 0}
    assert stats["count"] == 2
    assert stats["reward_mean"] == 0.19999999999999998
    assert stats["sector_counts"] == {"Technology": 1, "Financials": 1}
    assert stats["tier_counts"] == {"tier_1": 1, "tier_2": 1}
    assert stats["date_range"]["earliest"] <= stats["date_range"]["latest"]
