"""Quantified impact: the analyst shows its working, code re-checks it.

Each estimate on a card carries a formula over named inputs, and each input
says whether it came from the FILING, from MEMORY, or is an explicit
ASSUMPTION. This module:

* evaluates the formula with a tiny whitelisted arithmetic evaluator (no
  eval: numbers, input names, + - * / **, parentheses, abs/min/max/round);
* compares the result with the one the model stated (2% tolerance);
* checks every FILING / MEMORY input against the source text, so an input
  the model claims came from the filing must actually be there.

A stated result that its own formula does not reproduce is a MISMATCH, and
the card is flagged for review.
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass, field

from .grounding import SourceIndex
from .models import QuantifiedImpact

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"abs": abs, "min": min, "max": max, "round": round}
REL_TOLERANCE = 0.02


class FormulaError(ValueError):
    pass


def evaluate(formula: str, values: dict[str, float]) -> float:
    try:
        tree = ast.parse(formula.replace("×", "*").replace("÷", "/").replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"unparseable formula: {formula!r}") from exc

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise FormulaError(f"unknown input {node.id!r}")
            return float(values[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 4 or abs(left) > 1e6):
                raise FormulaError("exponent out of range")
            try:
                return _BINARY[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise FormulaError("division by zero") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
                and not node.keywords and 0 < len(node.args) <= 6):
            args = [walk(a) for a in node.args]
            if node.func.id == "round":
                args = args[:1] + [int(a) for a in args[1:2]]
            try:
                return float(_FUNCS[node.func.id](*args))
            except (TypeError, ValueError) as exc:
                raise FormulaError(f"bad arguments to {node.func.id}") from exc
        raise FormulaError(f"unsupported expression: {ast.dump(node)[:60]}")

    result = walk(tree)
    if not math.isfinite(result):
        raise FormulaError("non-finite result")
    return result


def _decimals(value: float) -> int:
    text = f"{value:.10g}"
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


@dataclass
class QuantCheck:
    items: list[dict] = field(default_factory=list)
    checked_inputs: int = 0
    unsourced: list[str] = field(default_factory=list)
    mismatches: int = 0


def check(estimates: list[QuantifiedImpact], *sources: str) -> QuantCheck:
    index = SourceIndex(*sources)
    out = QuantCheck()
    for est in estimates[:5]:
        item = est.model_dump()
        values = {i.name: i.value for i in est.inputs if i.value is not None}
        flags = []
        for i in est.inputs:
            if i.source in ("FILING", "MEMORY") and i.value is not None:
                out.checked_inputs += 1
                if not index.grounded(abs(i.value), _decimals(i.value), is_percent=False):
                    flags.append(i.name)
                    out.unsourced.append(f"{i.name}={i.value:g}")
        item["unsourced_inputs"] = flags
        try:
            computed = evaluate(est.formula, values)
        except FormulaError as exc:
            item.update(check="UNCHECKED", computed=None, check_note=str(exc))
            out.items.append(item)
            continue
        item["computed"] = round(computed, 6)
        if est.result is None:
            item.update(result=round(computed, 4), check="VERIFIED")
        elif math.isclose(computed, est.result, rel_tol=REL_TOLERANCE, abs_tol=0.05):
            item["check"] = "VERIFIED"
        else:
            item["check"] = "MISMATCH"
            item["check_note"] = f"formula gives {computed:,.4g}, card states {est.result:,.4g}"
            out.mismatches += 1
        out.items.append(item)
    return out
