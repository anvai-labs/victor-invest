"""Evaluate simple arithmetic formulas without executing arbitrary code.

Metric extraction defines derived figures as small formulas -- "total_revenue -
gross_profit" and similar. Callers substitute numeric values for the names and
then need the arithmetic evaluated.

That was previously done with ``eval``. Two variants existed: one passed
``{"__builtins__": {}}``, which is escapable through attribute chains such as
``().__class__.__bases__``, and one relied on a character allowlist, which is only
as strong as the allowlist. Neither was reachable in practice, because formulas
come from mapping configuration rather than user input -- but both are the shape
that becomes a vulnerability as soon as that configuration becomes editable.

This parses the expression and walks the AST, permitting arithmetic nodes only.
Anything else -- a name, a call, an attribute, a comprehension -- is rejected
before evaluation rather than filtered beforehand, so there is no allowlist to
get wrong.
"""

from __future__ import annotations

import ast
import logging
import operator
from typing import Any

logger = logging.getLogger(__name__)

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate_node(node: ast.AST) -> float:
    """Evaluate one arithmetic node, rejecting everything else."""
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            # bool is an int subclass; neither it nor strings belong in a formula.
            raise ValueError(f"non-numeric constant: {node.value!r}")
        return float(node.value)

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op(_evaluate_node(node.left), _evaluate_node(node.right))

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_evaluate_node(node.operand))

    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def evaluate_arithmetic(expression: str) -> float | None:
    """Evaluate *expression* as arithmetic over ``+ - * /`` and parentheses.

    Args:
        expression: The formula, with every name already replaced by its value.

    Returns:
        The result, or ``None`` if the expression is not pure arithmetic, is
        malformed, or cannot be evaluated (division by zero, overflow).
        Returning ``None`` rather than raising matches what both call sites did.
    """
    stripped = expression.strip() if expression else ""
    if not stripped:
        return None

    try:
        # Must be stripped: leading whitespace makes mode="eval" raise IndentationError,
        # so " 8 / 2 " would otherwise be rejected as malformed.
        tree = ast.parse(stripped, mode="eval")
    except SyntaxError:
        logger.debug("Formula is not a valid expression: %r", expression)
        return None

    try:
        return float(_evaluate_node(tree))
    except ValueError as exc:
        # Raised by the walk above for any non-arithmetic element.
        logger.debug("Refusing to evaluate %r: %s", expression, exc)
        return None
    except (ZeroDivisionError, OverflowError, TypeError) as exc:
        logger.debug("Formula %r could not be evaluated: %s", expression, exc)
        return None


def substitute_and_evaluate(formula: str, values: dict[str, Any]) -> float | None:
    """Replace names in *formula* with their values, then evaluate the arithmetic.

    Longer names are substituted first so that a short name is not replaced inside
    a longer one that contains it (for example ``revenue`` inside ``total_revenue``).
    """
    expression = formula
    for name in sorted(values, key=len, reverse=True):
        value = values[name]
        if value is None:
            continue
        expression = expression.replace(name, str(float(value)))

    return evaluate_arithmetic(expression)
