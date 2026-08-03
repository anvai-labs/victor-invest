from datetime import date

import numpy as np

from investigator.domain.services.rl.feature_extractor import (
    GICS_SECTORS,
    ValuationContextExtractor,
    get_feature_extractor,
)
from investigator.domain.services.rl.models import CompanySize, GrowthStage


class _Classifier:
    def __init__(self, result=None, raises=False):
        self.result = result or {"score": 0.77}
        self.raises = raises

    def classify(self, financials, ratios):
        if self.raises:
            raise ValueError("classifier unavailable")
        return self.result


def test_extract_builds_context_from_financials_market_and_insider_data():
    extractor = ValuationContextExtractor()

    context = extractor.extract(
        symbol="KR",
        financials={
            "sector": "Consumer Staples",
            "industry": "Grocery Stores",
            "market_cap": 40_000_000_000,
            "net_income": 2_100_000_000,
            "ebitda": 5_500_000_000,
            "free_cash_flow": 2_000_000_000,
            "total_revenue": 150_000_000_000,
            "quarterly_data": [{}, {}, {}, {}, {}],
            "fiscal_period": "FY2025",
        },
        ratios={
            "pe_ratio": 18,
            "revenue_growth": 0.04,
            "fcf_margin": 0.013,
            "payout_ratio": 0.42,
            "gross_margin": 0.22,
            "operating_margin": 0.035,
            "debt_to_equity": 4.2,
        },
        market_context={
            "trend_score": 0.4,
            "sentiment_score": -0.2,
            "volatility": 0.31,
            "technical_indicators": {
                "rsi_14": 62,
                "macd_histogram": 2.5,
                "obv_trend": 0.7,
                "adx_14": 33,
                "stoch_k": 71,
                "mfi_14": 58,
            },
            "entry_exit_signals": {
                "entry_signal_strength": 0.8,
                "exit_signal_strength": -0.3,
                "signal_confluence": 0.6,
                "days_from_support": 0.2,
                "risk_reward_ratio": 4.5,
            },
        },
        data_quality={"overall_score": 88},
        insider_data={
            "sentiment_score": 1.4,
            "buy_count": 3,
            "sell_count": 1,
            "buy_value": 14_000_000,
            "sell_value": 1_000_000,
            "cluster_detected": True,
            "key_insider_activity": [{"is_buy": True}, {"is_buy": False}, {"is_buy": True}],
        },
        current_price=72.0,
        analysis_date=date(2026, 5, 20),
    )

    assert context.symbol == "KR"
    assert context.analysis_date == date(2026, 5, 20)
    assert context.company_size == CompanySize.LARGE_CAP
    assert context.growth_stage == GrowthStage.DIVIDEND_PAYING
    assert context.net_margin == 0.014
    assert context.margin_bin == 0
    assert context.is_low_margin_industry is True
    assert context.debt_to_equity == 3.0
    assert context.insider_sentiment == 1.0
    assert context.insider_buy_ratio == 0.75
    assert context.insider_transaction_value == 1.0
    assert context.insider_cluster_signal == 1.0
    assert context.insider_key_exec_activity == 1 / 3
    assert context.ggm_applicable is True

    tensor = extractor.to_tensor(context)
    names = extractor.get_feature_names()
    assert isinstance(tensor, np.ndarray)
    assert len(tensor) == len(names)
    assert tensor.dtype == np.float32


def test_growth_stage_and_company_size_classification_branches():
    extractor = ValuationContextExtractor()

    assert extractor._classify_growth_stage({"net_income": -10, "ebitda": -1}, {}) == GrowthStage.PRE_PROFIT
    assert (
        extractor._classify_growth_stage({"net_income": 0, "ebitda": 1}, {"revenue_growth": 0.30})
        == GrowthStage.EARLY_GROWTH
    )
    assert (
        extractor._classify_growth_stage({"net_income": 10, "ebitda": 1}, {"revenue_growth": 0.30})
        == GrowthStage.HIGH_GROWTH
    )
    assert (
        extractor._classify_growth_stage({"net_income": 10, "ebitda": 1}, {"payout_ratio": 0.5})
        == GrowthStage.DIVIDEND_PAYING
    )
    assert (
        extractor._classify_growth_stage({"net_income": 10, "ebitda": 1}, {"revenue_growth": 0.15})
        == GrowthStage.TRANSITIONING
    )
    assert extractor._classify_growth_stage({"net_income": 10, "ebitda": 1}, {}) == GrowthStage.MATURE

    assert extractor._classify_company_size({"market_cap": 100_000_000}, None) == CompanySize.MICRO_CAP
    assert extractor._classify_company_size({"market_cap": 1_000_000_000}, None) == CompanySize.SMALL_CAP
    assert extractor._classify_company_size({"market_cap": 5_000_000_000}, None) == CompanySize.MID_CAP
    assert extractor._classify_company_size({"market_cap": 50_000_000_000}, None) == CompanySize.LARGE_CAP
    assert extractor._classify_company_size({"shares_outstanding": 4_000_000_000}, 100) == CompanySize.MEGA_CAP


def test_helper_methods_handle_bounds_unknowns_and_classifier_fallbacks():
    with_classifier = ValuationContextExtractor(profitability_classifier=_Classifier())
    failing_classifier = ValuationContextExtractor(profitability_classifier=_Classifier(raises=True))
    extractor = ValuationContextExtractor()

    assert with_classifier._calculate_profitability_score({}, {}) == 0.77
    assert 0.0 <= failing_classifier._calculate_profitability_score({}, {}) <= 1.0
    assert extractor._normalize_pe(None) == 0.5
    assert extractor._normalize_pe(4) == 0.1
    assert extractor._normalize_pe(120) == 1.0
    assert extractor._normalize_volatility(None) == 0.5
    assert extractor._normalize_volatility(0.01) == 0.0
    assert extractor._normalize_volatility(1.2) == 1.0
    assert extractor._normalize_macd_histogram(5, 0) == 0.0
    assert extractor._normalize_growth(-1.0) == 0.0
    assert extractor._normalize_growth(5.0) == 1.0
    assert extractor._normalize_margin(-1.0) == 0.0
    assert extractor._normalize_margin(1.0) == 1.0
    assert extractor._calculate_margin_bin(0.01) == 0
    assert extractor._calculate_margin_bin(0.03) == 1
    assert extractor._calculate_margin_bin(0.07) == 2
    assert extractor._calculate_margin_bin(0.12) == 3
    assert extractor._safe_get_float({"bad": "n/a"}, "bad", 9.0) == 9.0
    assert extractor._one_hot_sector("Not A Sector")[-1] == 1.0
    assert sum(extractor._one_hot_sector(GICS_SECTORS[0])) == 1.0


def test_insider_aggregate_and_applicability_paths():
    extractor = ValuationContextExtractor()

    insider = extractor._extract_insider_features(
        {
            "buy_count": 0,
            "sell_count": 2,
            "buy_value": 0,
            "sell_value": 12_000_000,
            "cluster_detected": True,
            "key_insider_buy_count": 1,
            "key_insider_sell_count": 3,
        }
    )
    applicability = extractor._determine_model_applicability(
        {"free_cash_flow": -1, "quarters_available": 2, "net_income": -5, "ebitda": -1},
        {"payout_ratio": 0.5},
        GrowthStage.PRE_PROFIT,
    )

    assert insider["buy_ratio"] == 0.0
    assert insider["transaction_value"] == -1.0
    assert insider["cluster_signal"] == -1.0
    assert insider["key_exec_activity"] == -0.5
    assert applicability == {"dcf": False, "ggm": False, "pe": False, "ps": True, "pb": True, "ev_ebitda": False}
    assert isinstance(get_feature_extractor(), ValuationContextExtractor)
