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
import re
from dataclasses import dataclass, field

from .grounding import SourceIndex
from .models import QuantifiedImpact

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"abs": abs, "min": min, "max": max, "round": round}
REL_TOLERANCE = 0.02


# What one of each unit is in units of its currency (or of itself), so a formula over mixed units is checked in one
# scale: Texmaco's USD 135M x ₹85 was stated as ₹11,475 Cr and passed, being 135 x 85 (round 5 arm B, 2026-10-19).
_UNIT_SIZE = {"INR": 1, "RS": 1, "USD": 1, "EUR": 1, "GBP": 1, "JPY": 1, "AED": 1, "PCT": 1, "%": 1, "X": 1, "TIMES": 1,
              "NUMBER": 1, "COUNT": 1, "SHARES": 1, "INR_PER_SHARE": 1,
              "INR_CR": 1e7, "CR": 1e7, "CRORE": 1e7, "INR_LAKH": 1e5, "LAKH": 1e5, "INR_TH": 1e3, "INR_THOUSAND": 1e3,
              "INR_M": 1e6, "INR_MN": 1e6, "INR_MILLION": 1e6, "INR_BN": 1e9, "INR_BILLION": 1e9,
              "USD_M": 1e6, "USD_MN": 1e6, "USD_MILLION": 1e6, "USD_BN": 1e9, "USD_BILLION": 1e9, "USD_K": 1e3,
              "EUR_M": 1e6, "EUR_MN": 1e6, "EUR_BN": 1e9, "SHARES_CR": 1e7, "SHARES_LAKH": 1e5, "SHARES_M": 1e6,
              # an exchange rate is rupees per one unit of the currency: Sagility's US$ 20 M x 89 "INR/USD" was stated as
              # ₹1,780 Cr and passed with the rate's unit unknown (live audit, 22 Oct 2026; it is ₹178 Cr)
              **{f"{a}_PER_{b}": 1 for a in ("INR", "RS", "USD") for b in ("USD", "EUR", "GBP", "JPY", "AED", "INR")}}


_NAMES = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_LITERAL = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_MULTIPLIERS = {2.0, 3.0, 4.0, 12.0}   # halves, quarters and months to a year


def _size(unit: str | None) -> float | None:
    return _UNIT_SIZE.get(str(unit or "").strip().upper().replace(" ", "_").replace("/", "_PER_"))


_COUNT_WORDS = (("BILLION", 1e9), ("CRORE", 1e7), ("MILLION", 1e6), ("LAKH", 1e5), ("THOUSAND", 1e3))


def _with_counts(est: QuantifiedImpact, values: dict[str, float]) -> float | None:
    """The formula with each input multiplied by the count word its unit spells out ("million units", "lakh tonnes");
    None when no input has one."""
    counts = {i.name: next((n for word, n in _COUNT_WORDS if word in str(i.unit or "").upper()), 1.0) for i in est.inputs}
    if all(c == 1.0 for c in counts.values()):
        return None
    try:
        return evaluate(est.formula, {k: v * counts.get(k, 1.0) for k, v in values.items()})
    except (FormulaError, ZeroDivisionError, OverflowError):
        return None


def in_units(est: QuantifiedImpact) -> float | None:
    """The formula evaluated with every input at its unit's size and the answer in the result's unit; None when a unit
    is not known (then only the plain arithmetic is checked, as before)."""
    sizes = {i.name: _size(i.unit) for i in est.inputs if i.value is not None}
    out = _size(est.unit)
    formula = est.formula or ""
    units = [str(i.unit or "").upper() for i in est.inputs] + [str(est.unit or "").upper()]
    if out is None or not sizes or any(s is None for s in sizes.values())             or any(u in ("PCT", "%") for u in units)             or any(name not in formula for name in sizes)             or any(float(n) not in _MULTIPLIERS for n in _LITERAL.findall(_NAMES.sub(" ", formula))):
        # Only a plain product, quotient or sum of named amounts is put in units. Measured on 383 stored impacts
        # (2026-10-19): a formula that is a bare number ("6000"), one that converts itself ("/ 100" from lakh, "/ 1e7"),
        # or one over percentages was held wrongly; the three it caught (Texmaco's USD x ₹85, SKF's ₹ million x 4,
        # twice) are plain products.
        return None
    try:
        return evaluate(est.formula, {i.name: i.value * sizes[i.name] for i in est.inputs if i.value is not None}) / out
    except (FormulaError, ZeroDivisionError, OverflowError):
        return None


class FormulaError(ValueError):
    pass


def evaluate(formula: str, values: dict[str, float]) -> float:
    try:
        tree = ast.parse(formula.replace("×", "*").replace("÷", "/").replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"unparseable formula: {formula!r}") from exc

    # Models name an input "q3fy25_ebitda" and write "Q3FY25_EBITDA * 4" in the formula: same input.
    folded = {name.lower(): value for name, value in values.items()}

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in values:
                return float(values[node.id])
            if node.id.lower() in folded:
                return float(folded[node.id.lower()])
            raise FormulaError(f"unknown input {node.id!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1e6 or (left < 0 and not float(right).is_integer())):
                raise FormulaError("exponent out of range")
            try:
                return _BINARY[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise FormulaError("division by zero") from exc
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise FormulaError(f"arithmetic error: {exc}") from exc
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

    if sum(1 for _ in ast.walk(tree)) > 60:
        raise FormulaError("formula too long")
    try:
        result = walk(tree)
    except RecursionError as exc:
        raise FormulaError("formula too deeply nested") from exc
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
    # An estimate may build on an earlier one's verified result: Shivam's "exposure as a share of the FY25
    # loss" took the total exposure (₹50.1 Cr tax + ₹50.1 Cr penalty = ₹100.2 Cr) as its input, and that
    # input was reported as a figure the filing does not state (loop round 3a, 2026-10-17).
    results: list[float] = []
    for est in estimates[:5]:
        item = est.model_dump()
        values = {i.name: i.value for i in est.inputs if i.value is not None}
        flags = []
        for i in est.inputs:
            if i.source in ("FILING", "MEMORY") and i.value is not None:
                out.checked_inputs += 1
                if any(math.isclose(abs(i.value), abs(r), rel_tol=0.005, abs_tol=0.05) for r in results):
                    continue
                if not (index.stated(abs(i.value), _decimals(i.value)) or (abs(i.value) <= 31 and float(i.value).is_integer())):
                    flags.append(i.name)
                    out.unsourced.append(f"{i.name}={i.value:g}")
        item["unsourced_inputs"] = flags
        try:
            computed = evaluate(est.formula, values)
        except FormulaError as exc:
            item.update(check="UNCHECKED", computed=None, check_note=str(exc))
            out.items.append(item)
            continue
        scaled = in_units(est)
        if scaled is not None and not math.isclose(scaled, computed, rel_tol=REL_TOLERANCE, abs_tol=0.05):
            computed = scaled   # the units say what the plain product means; the stated result is held to that
        elif scaled is None and est.result is not None \
                and not math.isclose(computed, est.result, rel_tol=REL_TOLERANCE, abs_tol=0.05):
            # an input's count stated in its unit ("70" "million units") and the formula's own conversion ("/ 1e7"):
            # Jindal Stainless's 70 million units x ₹6.5 / 1e7 = ₹45.5 Cr was held as 4.55e-05 (owner's review, 2026-10-20)
            counted = _with_counts(est, values)
            if counted is not None and math.isclose(counted, est.result, rel_tol=REL_TOLERANCE, abs_tol=0.05):
                computed = counted
        item["computed"] = round(computed, 6)
        if est.result is None:
            item.update(result=round(computed, 4), check="VERIFIED")
        elif math.isclose(computed, est.result, rel_tol=REL_TOLERANCE, abs_tol=0.05):
            item["check"] = "VERIFIED"
        elif str(est.unit or "").upper() in ("PCT", "%") and math.isclose(computed * 100, est.result, rel_tol=REL_TOLERANCE,
                                                                         abs_tol=0.05):
            # a share written as a percentage of a formula that gives the fraction: Novartis's 53.29 / 103.81 = 0.513, the
            # card's 51.3%, DLF's -0.71%, Kilitch's 40.4% (held-card audit and the owner's review queue, 22 Oct 2026: 4 of
            # the stored 100x mismatches, every one in PCT and none a true error; the 10x ones stay held, half are real)
            item["computed"] = round(computed * 100, 6)
            item["check"] = "VERIFIED"
        else:
            item["check"] = "MISMATCH"
            item["check_note"] = f"formula gives {computed:,.4g}, card states {est.result:,.4g}"
            out.mismatches += 1
        if item["check"] == "VERIFIED" and not flags:
            results.append(computed)
        out.items.append(item)
    return out
