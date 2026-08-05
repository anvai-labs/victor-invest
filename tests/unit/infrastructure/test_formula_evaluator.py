"""The formula evaluator must compute arithmetic without executing arbitrary code.

Two call sites -- the canonical mapper and the metric-extraction orchestrator --
substitute numeric values into a formula string and then evaluated it with `eval`.
One guarded with `{"__builtins__": {}}`, which is escapable via attribute chains;
the other with a character allowlist, which is only as good as the allowlist.

Formulas come from mapping configuration rather than user input, so neither was
reachable in practice. They are the shape that becomes a vulnerability the moment
that configuration becomes editable, so the evaluator parses the expression and
walks the AST instead, permitting arithmetic nodes only.
"""

from __future__ import annotations

import pytest

from investigator.infrastructure.sec.formula_evaluator import evaluate_arithmetic


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2", 3.0),
        ("10 - 4", 6.0),
        ("3 * 4", 12.0),
        ("10 / 4", 2.5),
        ("(2 + 3) * 4", 20.0),
        ("-5 + 2", -3.0),
        ("+7", 7.0),
        ("1000000.5 - 0.5", 1000000.0),
        ("2 + 3 * 4", 14.0),  # precedence preserved
        ("  8   /   2  ", 4.0),  # whitespace tolerated
    ],
)
def test_evaluates_arithmetic(expression, expected):
    assert evaluate_arithmetic(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "lambda: 1",
        "[x for x in range(3)]",
        "print(1)",
        "total_revenue - gross_profit",  # unresolved variable names
        "1 if True else 2",
        "{'a': 1}",
        "1; 2",
    ],
)
def test_rejects_anything_that_is_not_arithmetic(expression):
    """Non-arithmetic input returns None rather than being executed."""
    assert evaluate_arithmetic(expression) is None


@pytest.mark.parametrize("expression", ["1 / 0", "5 // 0", "1 +", "", "   "])
def test_returns_none_for_unevaluable_input(expression):
    assert evaluate_arithmetic(expression) is None


def test_does_not_execute_side_effects(tmp_path):
    """A rejected expression must not run before being rejected."""
    marker = tmp_path / "written"
    expr = f"open({str(marker)!r}, 'w').write('x')"
    assert evaluate_arithmetic(expr) is None
    assert not marker.exists()
