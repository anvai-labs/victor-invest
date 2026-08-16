# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Investment Analysis Workflows.

This package provides workflow definitions for investment analysis tasks:
- Quick analysis (technical only)
- Standard analysis (technical + fundamental)
- Comprehensive analysis (full institutional-grade)
- RL backtest (historical backtesting)
- Peer comparison (relative valuation)

Uses Victor's YAML-first architecture with Python escape hatches for complex
conditions and transforms that cannot be expressed in YAML.

Example:
    from victor_invest.workflows import InvestmentWorkflowProvider

    provider = InvestmentWorkflowProvider()

    # Agentic workflow execution (with LLM support)
    result = await provider.run_agentic_workflow(
        "comprehensive",
        context={"symbol": "AAPL"},
        provider="ollama",
        model="gpt-oss:20b",
    )
    if result.success:
        synthesis = result.context.get("synthesis")
        print(f"Recommendation: {synthesis.get('recommendation')}")

    # Compute-only workflow execution (no orchestrator needed)
    result = await provider.run_workflow_with_handlers(
        "comprehensive",
        context={"symbol": "AAPL"},
    )

Available workflows (all YAML-defined):
- quick: Technical analysis only (~5 seconds)
- standard: Technical + Fundamental (~30 seconds)
- comprehensive: Full institutional-grade analysis (~60 seconds)
- rl_backtest: Historical backtesting for RL training
- peer_comparison: Peer group relative analysis

Architecture Decision: Direct Tool Invocation + Context Stuffing
================================================================
This package follows Victor's architecture:
- Phase 1-2: Direct tool/handler calls (deterministic, no LLM)
- Phase 3: Single LLM inference with all data (context stuffing)

Handlers are defined in victor_invest.handlers and registered with Victor's
workflow handler registry. YAML workflows reference handlers by path.

Note on Execution Models:
- run_agentic_workflow(): Uses WorkflowExecutor with an orchestrator, for agent nodes
- run_workflow_with_handlers(): Compute handlers, via run_compiled_workflow below
- run_compiled_workflow(): victor's canonical compiled path
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from victor_contracts.workflow_runtime import BaseYAMLWorkflowProvider

if TYPE_CHECKING:
    from victor_contracts.workflow_runtime import WorkflowResult

from victor_invest.workflows.graphs import (
    build_comprehensive_graph,
    build_graph_for_mode,
    build_quick_graph,
    build_standard_graph,
    run_analysis,
    run_yaml_analysis,
)
from victor_invest.workflows.rl_backtest import (
    RLBacktestWorkflowState,
    build_rl_backtest_graph,
    generate_lookback_list,
    run_rl_backtest,
    run_rl_backtest_batch,
)
from victor_invest.workflows.state import AnalysisMode, AnalysisWorkflowState

logger = logging.getLogger(__name__)


class InvestmentWorkflowProvider(BaseYAMLWorkflowProvider):
    """Provides investment-specific workflows.

    Uses YAML-first architecture with Python escape hatches for complex
    conditions and transforms that cannot be expressed in YAML.

    Inherits from BaseYAMLWorkflowProvider which provides:
    - YAML workflow loading and caching
    - Escape hatches registration from victor_invest.escape_hatches
    - Unified workflow compilation via UnifiedWorkflowCompiler

    Example:
        provider = InvestmentWorkflowProvider()

        # List available workflows
        print(provider.get_workflow_names())

        # Agentic execution (with LLM synthesis via orchestrator)
        result = await provider.run_agentic_workflow(
            "comprehensive",
            context={"symbol": "AAPL"},
            provider="ollama",
        )

        # Compute-only execution (uses registered handlers)
        result = await provider.run_workflow_with_handlers(
            "comprehensive",
            context={"symbol": "AAPL"},
        )

    Execution Models:
        - run_agentic_workflow(): Full orchestrator support for agent nodes
        - run_workflow_with_handlers(): Compute handlers, delegating to the compiled path
        - run_compiled_workflow(): victor's canonical compiled path (inherited)
    """

    def _get_escape_hatches_module(self) -> str:
        """Return the module path for investment escape hatches.

        Returns:
            Module path string for CONDITIONS and TRANSFORMS dictionaries
        """
        return "victor_invest.escape_hatches"

    def _get_workflows_directory(self) -> Path:
        """Return the directory containing YAML workflow files.

        Returns:
            Path to victor_invest/workflows/ directory
        """
        return Path(__file__).parent

    def get_auto_workflows(self) -> list[tuple[str, str]]:
        """Get automatic workflow triggers based on query patterns.

        Returns:
            List of (regex_pattern, workflow_name) tuples for auto-triggering
        """
        return [
            (r"quick\s+analysis", "quick"),
            (r"analyze\s+\w+\s+quickly", "quick"),
            (r"standard\s+analysis", "standard"),
            (r"analyze\s+stock", "standard"),
            (r"comprehensive\s+analysis", "comprehensive"),
            (r"full\s+analysis", "comprehensive"),
            (r"institutional.*analysis", "comprehensive"),
            (r"deep\s+dive", "comprehensive"),
            (r"backtest", "rl_backtest"),
            (r"rl\s+training", "rl_backtest"),
            (r"peer\s+comparison", "peer_comparison"),
            (r"compare.*peers", "peer_comparison"),
            (r"relative\s+valuation", "peer_comparison"),
        ]

    def get_workflow_for_task_type(self, task_type: str) -> str | None:
        """Get appropriate workflow for task type.

        Args:
            task_type: Type of task (e.g., "analysis", "backtest")

        Returns:
            Workflow name string or None if no mapping exists
        """
        mapping = {
            "quick": "quick",
            "standard": "standard",
            "comprehensive": "comprehensive",
            "analysis": "standard",
            "research": "comprehensive",
            "backtest": "rl_backtest",
            "rl": "rl_backtest",
            "peer": "peer_comparison",
            "comparison": "peer_comparison",
        }
        return mapping.get(task_type.lower())

    async def run_agentic_workflow(
        self,
        workflow_name: str,
        context: dict[str, Any] | None = None,
        provider: str = "ollama",
        model: str | None = None,
        timeout: float | None = None,
    ) -> "WorkflowResult":
        """Execute a YAML workflow with full agent node support.

        Uses Victor's public Agent.create() API for proper orchestrator creation,
        enabling agent nodes for LLM reasoning. This approach:
        - Leverages Victor's unified provider abstraction
        - Applies vertical-specific configuration automatically
        - Follows the framework's golden path for agent creation

        For compute-only workflows, use the simpler `run_workflow()` method
        inherited from BaseYAMLWorkflowProvider.

        Args:
            workflow_name: Name of the YAML workflow (e.g., "comprehensive")
            context: Initial context data (e.g., {"symbol": "AAPL"})
            provider: LLM provider ("ollama", "anthropic", "openai")
            model: Model identifier. If None, uses provider default.
            timeout: Optional overall timeout in seconds (default: 300)

        Returns:
            WorkflowResult with execution outcome and outputs

        Raises:
            ValueError: If workflow_name is not found

        Example:
            provider = InvestmentWorkflowProvider()
            result = await provider.run_agentic_workflow(
                "comprehensive",
                {"symbol": "AAPL"},
                provider="ollama",
                model="gpt-oss:20b",
            )
            if result.success:
                synthesis = result.context.get("synthesis")
                print(f"Recommendation: {synthesis.get('recommendation')}")
        """
        from victor_contracts.workflow_runtime import WorkflowExecutor

        from victor_invest.framework_bootstrap import create_investment_orchestrator

        workflow = self.get_workflow(workflow_name)
        if not workflow:
            raise ValueError(f"Unknown workflow: {workflow_name}")

        orchestrator = await create_investment_orchestrator(
            provider=provider,
            model=model,
            ensure_handlers=ensure_handlers_registered,
            warning_callback=logger.warning,
        )

        # Create executor with proper orchestrator
        executor = WorkflowExecutor(
            orchestrator,
            max_parallel=4,
            default_timeout=timeout or 300.0,
        )

        # Execute workflow with initial context
        return await executor.execute(
            workflow,
            initial_context=context or {},
            timeout=timeout,
        )

    async def run_workflow_with_handlers(
        self,
        workflow_name: str,
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> "WorkflowResult":
        """Execute a YAML workflow using registered compute handlers.

        Delegates to victor's ``run_compiled_workflow`` and adapts the result to
        the ``WorkflowResult`` shape callers already read.

        This used to build its own executor: a ``_MinimalOrchestrator`` placeholder,
        a hand-populated ToolRegistry, and a direct ``WorkflowExecutor(...)``
        construction. victor has since renamed that class to
        ``CompiledWorkflowExecutor`` and dropped the ``tool_registry`` parameter, so
        the call raised TypeError on every invocation. ``run_analysis`` catches every
        Exception and degrades to StateGraph, which meant the documented primary
        engine was dead and only said so at WARNING level.

        Reimplementing the framework's own executor is what made that possible: a
        private copy of someone else's constructor is a copy that goes stale
        silently. The compiled path runs the same compute handlers -- verified by
        node_history showing every node execute -- and is maintained upstream.

        Args:
            workflow_name: Name of the YAML workflow (e.g., "comprehensive")
            context: Initial context data (e.g., {"symbol": "AAPL"})
            timeout: Accepted for backward compatibility. The compiled path takes
                its timeout from the workflow definition, so this is not forwarded.

        Returns:
            WorkflowResult with execution outcome and outputs

        Raises:
            ValueError: If workflow_name is not found

        Example:
            provider = InvestmentWorkflowProvider()
            result = await provider.run_workflow_with_handlers(
                "comprehensive",
                context={"symbol": "AAPL"},
            )
            if result.success:
                synthesis = result.context.get("synthesis")
        """
        from victor_contracts.workflow_runtime import WorkflowResult

        # Ensure handlers are registered
        ensure_handlers_registered()

        # Preserved from the old contract: callers rely on an unknown name raising
        # ValueError rather than surfacing as a failed result.
        if not self.get_workflow(workflow_name):
            raise ValueError(f"Unknown workflow: {workflow_name}")

        if timeout is not None:
            logger.debug(
                "timeout=%s is not forwarded to the compiled path; the workflow definition owns it",
                timeout,
            )

        graph_result = await self.run_compiled_workflow(workflow_name, context=context or {})

        state = graph_result.state if isinstance(graph_result.state, dict) else {}
        error = graph_result.error
        return WorkflowResult(
            workflow_name=workflow_name,
            success=bool(graph_result.success),
            context=state,
            total_duration=float(getattr(graph_result, "duration", 0.0) or 0.0),
            # The compiled path does not report a tool-call count; 0 is the honest
            # value rather than a fabricated one.
            total_tool_calls=0,
            error=str(error) if error else None,
        )

    # Inherited from BaseYAMLWorkflowProvider:
    # - run_compiled_workflow(): Uses UnifiedWorkflowCompiler (LangGraph)
    # - stream_compiled_workflow(): Streams via UnifiedWorkflowCompiler
    # - compile_workflow(): Returns CachedCompiledGraph for manual execution


# Lazy handler registration to prevent circular imports
_handlers_registered = False


def ensure_handlers_registered() -> None:
    """Register Investment domain handlers lazily on first use.

    This lazy registration pattern prevents circular imports that can occur
    when handlers.py imports from workflows or related modules during module
    initialization. Handlers are registered once on first workflow execution.
    """
    global _handlers_registered
    if _handlers_registered:
        return
    from victor_invest.handlers import register_handlers

    register_handlers()

    synced = False
    sync_method_used = None

    # There is no sync_handlers_with_executor anywhere in victor-ai. The deprecated
    # contracts bridge advertised one in its lazy-import map, but the target module
    # never exported it, so that import always raised and this registry path is what
    # has actually been running.
    if not synced:
        try:
            from victor.framework.handler_registry import get_handler_registry

            registry = get_handler_registry()
            sync_method = getattr(registry, "sync_with_executor", None)
            if callable(sync_method):
                sync_method(direction="to_executor")
                synced = True
                sync_method_used = "registry.sync_with_executor"
        except Exception:
            logger.debug("ensure_handlers_registered: suppressed error", exc_info=True)

    if not synced:
        # Last-resort bridge: push handlers from framework registry to
        # executor registry directly when helper APIs are unavailable.
        try:
            from victor.framework.handler_registry import get_handler_registry
            from victor_contracts.workflow_runtime import register_compute_handler

            registry = get_handler_registry()
            # list_handlers returns Dict[str, List[str]] mapping vertical names to handler names
            handlers_map = registry.list_handlers()
            pushed = 0
            for vertical_name, handler_names in handlers_map.items():
                for handler_name in handler_names:
                    handler = registry.get_handler(vertical_name, handler_name)
                    if handler:
                        register_compute_handler(handler_name, handler)
                        pushed += 1
            synced = pushed > 0
            sync_method_used = "manual_executor_bridge"
        except Exception:
            logger.debug("ensure_handlers_registered: suppressed error", exc_info=True)

    if not synced:
        logger.warning(
            "Handler sync helpers unavailable; relying on decorator-side registration for executor compatibility"
        )
    else:
        logger.debug("Handler sync completed using %s", sync_method_used)

    _handlers_registered = True


__all__ = [
    # Analysis state definitions
    "AnalysisMode",
    "AnalysisWorkflowState",
    # YAML-first workflow provider
    "InvestmentWorkflowProvider",
    # RL Backtest state
    "RLBacktestWorkflowState",
    "build_comprehensive_graph",
    # Analysis graph builders (Python-based, for backwards compatibility)
    "build_graph_for_mode",
    "build_quick_graph",
    # RL Backtest graph builders
    "build_rl_backtest_graph",
    "build_standard_graph",
    # Lazy handler registration
    "ensure_handlers_registered",
    "generate_lookback_list",
    # Analysis convenience
    "run_analysis",
    # RL Backtest convenience
    "run_rl_backtest",
    "run_rl_backtest_batch",
    "run_yaml_analysis",
]
