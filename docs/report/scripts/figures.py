#!/usr/bin/env python3
"""figures.py — the report's numbers, resolved from figures.yaml.

Every currency figure the report prints lives in docs/report/figures.yaml as
either a measured leaf (value + source) or a formula over other figures. This
module resolves the formulas and formats the results the way the documents
print them. No arithmetic belongs in the prose, and none belongs here either:
the formulas are data.

Usage:
    ./figures.py                 every figure, grouped
    ./figures.py block_b_total   one figure, bare value
    ./figures.py --group totals

Formulas accept + - * / parentheses and names of other figures. Anything else
is rejected rather than evaluated.
"""

import argparse
import ast
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "figures.yaml"

GROUP_ORDER = [
    "a_fixed",
    "a_variable",
    "b_fixed",
    "b_variable",
    "totals",
    "rates_derived",
    "right_sized",
    "errors",
    "marginal",
    "amortization",
    "architecture",
    "guardrails",
    "campaign_0905",
    "inference_points",
    "d23",
]

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


class _Pending:
    def __repr__(self):
        return "pending"


PENDING = _Pending()


class FigureError(Exception):
    pass


def load(path=None):
    path = pathlib.Path(path) if path else DEFAULT_PATH
    with open(path) as handle:
        doc = yaml.safe_load(handle)
    if "figures" not in doc:
        raise FigureError(f"{path} has no 'figures' mapping")
    return doc


def _eval(node, figures, resolved, stack):
    if isinstance(node, ast.Expression):
        return _eval(node.body, figures, resolved, stack)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FigureError(f"non-numeric constant {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        return _resolve_one(node.id, figures, resolved, stack)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _eval(node.operand, figures, resolved, stack)
        return PENDING if operand is PENDING else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval(node.left, figures, resolved, stack)
        right = _eval(node.right, figures, resolved, stack)
        if left is PENDING or right is PENDING:
            return PENDING
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise FigureError("division by zero")
        return left / right
    raise FigureError(f"unsupported expression node {type(node).__name__}")


def _resolve_one(name, figures, resolved, stack):
    if name in resolved:
        return resolved[name]
    if name not in figures:
        raise FigureError(f"unknown figure '{name}'")
    if name in stack:
        raise FigureError("cycle: " + " -> ".join(list(stack) + [name]))
    spec = figures[name] or {}
    if spec.get("pending"):
        resolved[name] = PENDING
        return PENDING
    if "value" in spec:
        value = float(spec["value"])
    elif "formula" in spec:
        tree = ast.parse(str(spec["formula"]), mode="eval")
        value = _eval(tree, figures, resolved, stack + [name])
    else:
        raise FigureError(f"figure '{name}' has neither value nor formula")
    resolved[name] = value
    return value


def resolve(doc):
    figures = doc["figures"]
    resolved = {}
    for name in figures:
        _resolve_one(name, figures, resolved, [])
    return resolved


def display(name, value, doc):
    if value is PENDING:
        return "pending"
    spec = doc["figures"].get(name) or {}
    decimals = spec.get("display", 2)
    unit = str(spec.get("unit", ""))
    if unit in ("hours",):
        decimals = spec.get("display", 0)
    return f"{value:,.{decimals}f}"


def main():
    parser = argparse.ArgumentParser(description="resolve docs/report/figures.yaml")
    parser.add_argument("name", nargs="?", help="print one figure and exit")
    parser.add_argument("--group", help="print one group only")
    parser.add_argument("--path", help="alternative figures.yaml")
    args = parser.parse_args()

    doc = load(args.path)
    values = resolve(doc)
    figures = doc["figures"]

    if args.name:
        if args.name not in values:
            print(f"unknown figure '{args.name}'", file=sys.stderr)
            return 2
        print(display(args.name, values[args.name], doc))
        return 0

    groups = {}
    for name, spec in figures.items():
        group = (spec or {}).get("group", "inputs")
        groups.setdefault(group, []).append(name)

    order = [g for g in GROUP_ORDER if g in groups]
    order += [g for g in groups if g not in GROUP_ORDER]
    if args.group:
        order = [g for g in order if g == args.group]

    for group in order:
        print(f"\n{group}")
        for name in groups[group]:
            spec = figures[name] or {}
            basis = spec.get("formula") or spec.get("source", "")
            print(f"  {display(name, values[name], doc):>14}  {name:<28} {basis}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
