"""TRANSFORM.md "Held codes" against the code (offline): every hold / reason code the transform, the placement and
dedupe can produce has its row in the doc's table, and every row of the table is a code the code produces.

The codes are read from the source with a narrow AST scan (the modules keep no list of them):
  * transform.py, run_transform.py: a dict {"code": "<literal>"} that goes into a `held` list (`held.append(...)`,
    `p["held"].append(...)`, or inside the value of a "held" key);
  * placement.py: the literal values of "status" in place(), but "placed";
  * dedupe.py: the literal values of "decision" in Index.decide().
"""
import ast
import os
import re
from typing import Iterator

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(SCRIPTS, "TRANSFORM.md")


def _tree(name: str) -> ast.Module:
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as f:
        return ast.parse(f.read(), name)


def _strings(node: ast.AST) -> Iterator[str]:
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def _code_dicts(node: ast.AST) -> Iterator[str]:
    """The literal "code" of every {"code": ...} dict under node."""
    for n in ast.walk(node):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == "code" and isinstance(v, ast.Constant) \
                        and isinstance(v.value, str):
                    yield v.value


def _is_held(target: ast.AST) -> bool:
    """`held` or `<anything>["held"]`."""
    return (isinstance(target, ast.Name) and target.id == "held") or \
        (isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value == "held")


def held_codes(name: str) -> set[str]:
    codes: set[str] = set()
    for n in ast.walk(_tree(name)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append" \
                and _is_held(n.func.value):
            for arg in n.args:
                codes |= set(_code_dicts(arg))
        elif isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == "held":
                    codes |= set(_code_dicts(v))
    return codes


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(found) == 1, f"{name}: {len(found)} definitions"
    return found[0]


def keyed_values(fn: ast.AST, key: str) -> set[str]:
    """The string literals given to `key` in the dicts of fn (a conditional expression's both sides too)."""
    out: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    out |= set(_strings(v))
    return out


def code_side() -> set[tuple[str, str]]:
    transform = held_codes("transform.py") | held_codes("run_transform.py")
    placement = keyed_values(_function(_tree("placement.py"), "place"), "status") - {"placed"}
    dedupe = keyed_values(_function(_tree("dedupe.py"), "decide"), "decision")
    return {("transform", c) for c in transform} | {("placement", c) for c in placement} | \
        {("dedupe", c) for c in dedupe}


def doc_side() -> set[tuple[str, str]]:
    """(stage, code) of each row of the table under "## Held codes": the first cell a `code`, the second cell's
    first word its stage."""
    with open(DOC, encoding="utf-8") as f:
        text = f.read()
    start = text.index("\n## Held codes\n")
    end = text.find("\n## ", start + 1)
    section = text[start:end if end != -1 else None]
    rows = set()
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|\s*([a-z]+)", line)
        if m:
            rows.add((m.group(2), m.group(1)))
    return rows


def test_the_scan_finds_codes() -> None:
    # a scan that finds nothing would make the comparison pass on an empty table: known codes of each stage
    code = code_side()
    assert {("transform", "single_only"), ("transform", "agency_no_brand"), ("transform", "collect_incomplete"),
            ("placement", "unresolved"), ("placement", "no_profile"), ("dedupe", "duplicate_of")} <= code


def test_doc_table_matches_the_code() -> None:
    code, doc = code_side(), doc_side()
    assert not code - doc, f"codes with no row in TRANSFORM.md 'Held codes': {sorted(code - doc)}"
    assert not doc - code, f"rows of TRANSFORM.md 'Held codes' no code produces: {sorted(doc - code)}"
