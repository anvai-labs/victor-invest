import ast
from dataclasses import dataclass
from pathlib import Path

from victor_invest.tools.credit_risk import CreditRiskTool
from victor_invest.tools.insider_trading import InsiderTradingTool
from victor_invest.tools.market_data import MarketDataTool
from victor_invest.tools.market_regime import MarketRegimeTool
from victor_invest.tools.rl_backtest import RLBacktestTool
from victor_invest.tools.sec_filing import SECFilingTool
from victor_invest.tools.short_interest import ShortInterestTool
from victor_invest.tools.technical_indicators import TechnicalIndicatorsTool
from victor_invest.tools.valuation import ValuationTool

RUNTIME_FILES = (
    Path("victor_invest/handlers.py"),
    Path("victor_invest/api/app.py"),
    Path("victor_invest/workflows/graphs.py"),
    Path("victor_invest/workflows/rl_backtest.py"),
    Path("victor_invest/tools/valuation.py"),
    Path("victor_invest/tools/valuation_signals.py"),
)

ACTION_TOOLS = {
    "SECFilingTool": SECFilingTool,
    "MarketDataTool": MarketDataTool,
    "TechnicalIndicatorsTool": TechnicalIndicatorsTool,
    "RLBacktestTool": RLBacktestTool,
    "CreditRiskTool": CreditRiskTool,
    "InsiderTradingTool": InsiderTradingTool,
    "ShortInterestTool": ShortInterestTool,
    "MarketRegimeTool": MarketRegimeTool,
}

NON_ACTION_TOOLS = {
    "ValuationTool": ValuationTool,
}

HELPER_TOOL_FACTORIES = {
    "_get_sec_tool": "SECFilingTool",
    "_get_market_tool": "MarketDataTool",
    "_get_technical_tool": "TechnicalIndicatorsTool",
    "_get_valuation_tool": "ValuationTool",
    "_get_rl_backtest_tool": "RLBacktestTool",
}


@dataclass(frozen=True)
class ExecuteCall:
    path: Path
    lineno: int
    tool_ctor: str
    has_action_keyword: bool
    action_literal: str | None


def _resolve_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _ExecuteCallVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, known_tools: set[str]) -> None:
        self._path = path
        self._known_tools = known_tools
        self._scopes: list[dict[str, str]] = [{}]
        self.calls: list[ExecuteCall] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scopes.append({})
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scopes.append({})
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        tool_ctor = self._tool_ctor_from_constructor_call(node.value)
        if tool_ctor:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._scopes[-1][target.id] = tool_ctor
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        tool_ctor = self._tool_ctor_from_constructor_call(node.value)
        if tool_ctor and isinstance(node.target, ast.Name):
            self._scopes[-1][node.target.id] = tool_ctor
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            tool_ctor = self._resolve_tool_ctor(node.func.value)
            if tool_ctor:
                action_kw = next(
                    (kw for kw in node.keywords if kw.arg == "action"), None
                )
                action_literal = None
                if (
                    action_kw
                    and isinstance(action_kw.value, ast.Constant)
                    and isinstance(action_kw.value.value, str)
                ):
                    action_literal = action_kw.value.value

                self.calls.append(
                    ExecuteCall(
                        path=self._path,
                        lineno=node.lineno,
                        tool_ctor=tool_ctor,
                        has_action_keyword=action_kw is not None,
                        action_literal=action_literal,
                    )
                )
        self.generic_visit(node)

    def _tool_ctor_from_constructor_call(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Await):
            return self._tool_ctor_from_constructor_call(node.value)

        if not isinstance(node, ast.Call):
            return None

        ctor = _resolve_name(node.func)
        if ctor in self._known_tools:
            return ctor
        if ctor in HELPER_TOOL_FACTORIES:
            return HELPER_TOOL_FACTORIES[ctor]
        return None

    def _resolve_tool_ctor(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self._lookup(node.id)
        if isinstance(node, ast.Call):
            return self._tool_ctor_from_constructor_call(node)
        return None

    def _lookup(self, variable_name: str) -> str | None:
        for scope in reversed(self._scopes):
            if variable_name in scope:
                return scope[variable_name]
        return None


def _collect_execute_calls(path: Path, known_tools: set[str]) -> list[ExecuteCall]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _ExecuteCallVisitor(path, known_tools)
    visitor.visit(tree)
    return visitor.calls


def _load_action_enums() -> dict[str, set[str]]:
    action_enums: dict[str, set[str]] = {}
    for tool_ctor, tool_cls in ACTION_TOOLS.items():
        schema = tool_cls().get_schema()
        enum_values = schema.get("properties", {}).get("action", {}).get("enum", [])
        action_enums[tool_ctor] = {str(value) for value in enum_values}
    return action_enums


def test_runtime_tools_expose_expected_schema_contracts():
    action_enums = _load_action_enums()

    for tool_ctor, enum_values in action_enums.items():
        assert enum_values, f"{tool_ctor} must expose non-empty action enum in schema"

    valuation_schema = ValuationTool().get_schema()
    assert "action" not in valuation_schema.get("properties", {})
    assert valuation_schema.get("properties", {}).get("model", {}).get("enum")


def test_runtime_execute_calls_follow_tool_action_contracts():
    known_tools = set(ACTION_TOOLS) | set(NON_ACTION_TOOLS)
    action_enums = _load_action_enums()

    execute_calls: list[ExecuteCall] = []
    for path in RUNTIME_FILES:
        execute_calls.extend(_collect_execute_calls(path, known_tools))

    assert len(execute_calls) >= 14, (
        "Expected to discover runtime execute calls for contract coverage"
    )

    violations: list[str] = []

    for call in execute_calls:
        if call.tool_ctor in action_enums:
            if call.has_action_keyword and call.action_literal is not None:
                if call.action_literal not in action_enums[call.tool_ctor]:
                    violations.append(
                        f"{call.path}:{call.lineno} invalid action '{call.action_literal}' for {call.tool_ctor}"
                    )
            continue

        if call.tool_ctor in NON_ACTION_TOOLS and call.has_action_keyword:
            violations.append(
                f"{call.path}:{call.lineno} should not pass action=... to {call.tool_ctor}"
            )

    assert not violations, "Tool action contract violations:\n" + "\n".join(violations)
