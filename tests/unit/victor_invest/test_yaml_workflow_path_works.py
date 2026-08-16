"""The YAML workflow path must actually run, not fall back to StateGraph.

CLAUDE.md describes YAML workflows as the primary execution path, with
StateGraph as a fallback "when the YAML path fails unexpectedly". It was failing
on every single invocation:

    TypeError: CompiledWorkflowExecutor.__init__() got an unexpected keyword
               argument 'tool_registry'

`run_workflow_with_handlers` hand-rolled an executor -- a `_MinimalOrchestrator`
placeholder, a tool registry, and a direct `WorkflowExecutor(...)` construction.
victor has since renamed that class to `CompiledWorkflowExecutor` and dropped the
`tool_registry` parameter, so the call raised. `run_analysis` catches every
Exception and degrades to StateGraph with a warning, so the documented primary
engine was dead and nothing said so above log level WARNING.

These tests pin the fixed behaviour: the YAML path runs its compute handlers, and
the fallback is reserved for genuine failures.
"""

from __future__ import annotations

import logging

import pytest

from victor_invest.workflows import InvestmentWorkflowProvider, ensure_handlers_registered


@pytest.fixture(autouse=True)
def _handlers():
    ensure_handlers_registered()


@pytest.mark.asyncio
async def test_run_workflow_with_handlers_executes_rather_than_raising():
    """The regression itself: this call used to raise TypeError every time."""
    provider = InvestmentWorkflowProvider()

    result = await provider.run_workflow_with_handlers("quick", context={"symbol": "AAPL"})

    assert result.success, f"workflow failed: {result.error}"
    assert result.workflow_name == "quick"


@pytest.mark.asyncio
async def test_compute_handlers_actually_ran():
    """Success is not enough -- an empty graph would also 'succeed'."""
    provider = InvestmentWorkflowProvider()

    result = await provider.run_workflow_with_handlers("quick", context={"symbol": "AAPL"})

    context = result.context if isinstance(result.context, dict) else {}
    assert "market_data" in context, (
        f"no handler output in context (keys: {sorted(context)}); the workflow ran but computed nothing"
    )
    assert context.get("symbol") == "AAPL", "the initial context did not reach the handlers"


@pytest.mark.asyncio
async def test_the_result_still_looks_like_a_workflow_result():
    """Callers read .success/.context/.error; the shape must not change under them."""
    provider = InvestmentWorkflowProvider()

    result = await provider.run_workflow_with_handlers("quick", context={"symbol": "AAPL"})

    for attribute in ("workflow_name", "success", "context", "total_duration", "error"):
        assert hasattr(result, attribute), f"call sites read .{attribute}"


@pytest.mark.asyncio
async def test_an_unknown_workflow_still_raises_valueerror():
    """The old contract raised ValueError for an unknown name; keep it."""
    provider = InvestmentWorkflowProvider()

    with pytest.raises(ValueError):
        await provider.run_workflow_with_handlers("no-such-workflow", context={})


@pytest.mark.asyncio
async def test_run_analysis_does_not_fall_back_to_stategraph(caplog):
    """The fallback is for genuine failures, not for every single run."""
    from victor_invest.workflows.graphs import run_analysis
    from victor_invest.workflows.state import AnalysisMode

    with caplog.at_level(logging.WARNING):
        await run_analysis("AAPL", AnalysisMode.QUICK)

    fell_back = [r.getMessage() for r in caplog.records if "falling back to StateGraph" in r.getMessage()]
    assert not fell_back, f"the YAML path is still failing: {fell_back}"
