import asyncio

from investigator.domain.agents.symbol_update import SymbolUpdateAgent
from investigator.domain.models import AgentTask, AnalysisType, TaskStatus


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


def test_extract_metrics_captures_full_symbol_update_payload():
    agent = SymbolUpdateAgent("test_symbol_update")

    update_data = agent._extract_metrics(
        "MSFT",
        {
            "valuation": {
                "current_price": 400.0,
                "market_cap": 3_000_000_000_000,
                "company_profile": {"sector_median_ps": 10.0},
            },
            "fair_value": "440.123",
            "llm_fair_value_estimate": 435.44,
            "multi_model_summary": {
                "blended_fair_value": 445.0,
                "model_agreement_score": 0.88,
                "overall_confidence": 0.91,
                "applicable_models": 6,
                "divergence_flag": False,
                "tier_classification": "compounder",
                "fallback_applied": True,
                "models": [
                    {
                        "model": "dcf",
                        "fair_value_per_share": 450.0,
                        "applicable": True,
                        "assumptions": {"wacc": 0.09, "terminal_growth": 0.03, "projection_years": 5},
                        "metadata": {"rule_of_40": {"score": 51.2, "classification": "excellent"}},
                    },
                    {"model": "ggm", "fair_value_per_share": 410.0, "applicable": True},
                    {"model": "ps", "fair_value_per_share": 460.0, "applicable": True},
                    {"model": "pe", "fair_value_per_share": 455.0, "applicable": True},
                    {"model": "pb", "fair_value_per_share": 390.0, "applicable": True},
                    {"model": "ev_ebitda", "fair_value_per_share": 470.0, "applicable": True},
                    "not-a-model",
                ],
            },
            "ratios": {
                "price_to_sales": 12.0,
                "price_to_earnings": 32.0,
                "price_to_book": 11.0,
                "peg": 2.1,
                "ev_to_ebitda": 24.0,
                "debt_to_equity": 0.5,
                "free_cash_flow_margin": 0.31,
                "revenue_growth_rate": 0.14,
            },
            "quarterly_data": [
                {
                    "fiscal_year": 2026,
                    "fiscal_period": "Q1",
                    "financial_data": {
                        "revenue": 10,
                        "net_income": 2,
                        "operating_cash_flow": 3,
                        "free_cash_flow": 4,
                        "gross_profit": 5,
                        "ebitda": 6,
                        "total_assets": 7,
                        "total_liabilities": 8,
                        "stockholders_equity": 9,
                        "total_debt": 10,
                        "cash_and_cash_equivalents": 11,
                        "dividends_paid": 12,
                        "shares_outstanding": 13,
                        "public_float_usd": 800.0,
                        "current_price": 400.0,
                    },
                }
            ],
        },
        {
            "company_info": {
                "cik": "789019",
                "sector": "Technology",
                "industry": "Software",
                "sic": "7372",
            }
        },
    )

    assert update_data["mktcap"] == 3_000_000_000_000
    assert update_data["fair_value_blended"] == 445.0
    assert update_data["fair_value_dcf"] == 450.0
    assert update_data["fair_value_ev_ebitda"] == 470.0
    assert update_data["wacc"] == 0.09
    assert update_data["terminal_growth_rate"] == 0.03
    assert update_data["dcf_projection_years"] == 5
    assert update_data["rule_of_40_classification"] == "excellent"
    assert update_data["model_agreement_score"] == 0.88
    assert update_data["model_confidence"] == 0.91
    assert update_data["tier_classification"] == "compounder"
    assert update_data["fallback_weights_used"] is True
    assert update_data["valuation_models_json"]["llm_estimate"] == 435.44
    assert update_data["ps_premium_discount"] == 20.0
    assert update_data["float_shares"] == 2
    assert update_data["fiscal_period"] == "2026-Q1"
    assert update_data["cik"] == 789019
    assert update_data["sec_sector"] == "Technology"
    assert update_data["sic_code"] == 7372
    assert update_data["metrics_source"] == "sec_companyfacts"


def test_update_symbol_table_serializes_json_and_returns_rowcount(monkeypatch):
    agent = SymbolUpdateAgent("test_symbol_update")
    captured = {}

    class Result:
        rowcount = 1

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            captured["query"] = str(query)
            captured["params"] = params
            return Result()

        def commit(self):
            captured["committed"] = True

    class Engine:
        def connect(self):
            return Conn()

    monkeypatch.setattr(agent, "_get_stock_engine", lambda: Engine())

    rows = agent._update_symbol_table("AAPL", {"valuation_models_json": {"model": "pe"}, "pe_ratio": 20.0})

    assert rows == 1
    assert captured["committed"] is True
    assert captured["params"]["symbol"] == "AAPL"
    assert captured["params"]["valuation_models_json"] == '{"model": "pe"}'
    assert "UPDATE symbol" in captured["query"]


def test_pre_process_validates_required_fundamental_context():
    agent = SymbolUpdateAgent("test_symbol_update")
    task = AgentTask(
        task_id="task-1",
        symbol="AAPL",
        analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
        context={"fundamental_analysis": {"valuation": {}}, "sec_analysis": {"company_info": {}}},
    )

    assert asyncio.run(agent.pre_process(task)) is None


def test_process_returns_success_skip_and_failure(monkeypatch):
    agent = SymbolUpdateAgent("test_symbol_update")

    success_task = AgentTask(
        task_id="success",
        symbol="AAPL",
        analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
        context={"fundamental_analysis": {"valuation": {"market_cap": 1}}, "sec_analysis": {}},
    )
    monkeypatch.setattr(agent, "_update_symbol_table", lambda symbol, data: 1)

    success = asyncio.run(agent.process(success_task))

    assert success.status == TaskStatus.COMPLETED
    assert success.result_data["status"] == "success"
    assert success.result_data["rows_updated"] == 1

    skipped_task = AgentTask(
        task_id="skipped",
        symbol="MSFT",
        analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
        context={"fundamental_analysis": {}, "sec_analysis": {}},
    )
    skipped = asyncio.run(agent.process(skipped_task))

    assert skipped.status == TaskStatus.COMPLETED
    assert skipped.result_data["status"] == "skipped"

    def fail_update(symbol, data):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(agent, "_update_symbol_table", fail_update)
    failed = asyncio.run(agent.process(success_task))

    assert failed.status == TaskStatus.FAILED
    assert failed.metadata["error_type"] == "RuntimeError"
