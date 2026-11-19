"""Shared loaders for the slide, report, viva and consistency scripts.

Everything here reads files the game itself produced: results/experiments.json,
results/demo_seeds.json, docs/scenario/*.md, docs/ALGORITHMS.md, docs/RULES.md and the source
code (line numbers come from `ast`). Nothing is typed in by hand twice.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402, F401  (re-exported: build_*.py read K.C)

DOCS = ROOT / "docs"
SCEN = DOCS / "scenario"
RESULTS = ROOT / "results"
SCREENS = DOCS / "screens"
DIAGRAMS = DOCS / "diagrams"


# ------------------------------------------------------------------ experiments / seeds


def experiments() -> dict[str, dict]:
    """results/experiments.json: {E1: {games, rows: [[name, summary], ...]}, ...}."""
    return json.loads((RESULTS / "experiments.json").read_text(encoding="utf-8"))


def demo_seeds() -> dict:
    return json.loads((RESULTS / "demo_seeds.json").read_text(encoding="utf-8"))


EXPERIMENT_TITLES = {
    "E1": "Difficulty ladder",
    "E2": "A* vs greedy best-first (Tom's chase)",
    "E3": "DLS depth for Jerry's EVADE",
    "E4": "Fuzzy director vs always-HUNT",
    "E5": "Minimax and MCTS on/off",
    "E6": "Bruno on vs off",
}


def exp_header() -> list[str]:
    return [
        "Configuration",
        "Jerry win %",
        "Tom win %",
        "avg turns",
        "capture",
        "exit",
        "timeout",
        "Tom nodes/move",
        "Tom ms/move",
        "Jerry nodes/move",
        "Jerry ms/move",
    ]


def exp_row(name: str, s: dict) -> list[str]:
    """One table row exactly as shown in docs/RESULTS.md, the slides and the report."""
    c = s["causes"]
    return [
        name,
        f"{100 * s['jerry_win']:.0f}",
        f"{100 * s['tom_win']:.0f}",
        f"{s['avg_turns']:.1f}",
        str(c["capture"]),
        str(c["exit"]),
        str(c["timeout"]),
        f"{s['TOM']['avg_nodes']:.1f}",
        f"{s['TOM']['avg_ms']:.2f}",
        f"{s['JERRY']['avg_nodes']:.1f}",
        f"{s['JERRY']['avg_ms']:.2f}",
    ]


def results_conclusions() -> dict[str, str]:
    """The two-sentence conclusion of each experiment, read back from docs/RESULTS.md."""
    text = (DOCS / "RESULTS.md").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^## (E\d)\..*?\*\*Conclusion\.\*\* (.*?)$", text, re.S | re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


# ------------------------------------------------------------------ markdown blocks


@dataclass
class Block:
    kind: str  # h, p, table, code, img, ul, ol
    text: str = ""
    level: int = 0
    rows: list[list[str]] | None = None  # table: header + rows; ul/ol: not used
    items: list[str] | None = None
    path: Path | None = None  # img


def parse_md(path: Path) -> list[Block]:
    """Tiny markdown reader for the files this repo generates (headings, paragraphs, tables,
    fenced code, bullet / numbered lists, images, HTML comments skipped)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[Block] = []
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(Block("p", " ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(Block("code", "\n".join(code)))
        elif ln.startswith("<!--"):
            flush()
        elif m := re.match(r"^(#{1,6}) (.*)", ln):
            flush()
            out.append(Block("h", m.group(2).strip(), level=len(m.group(1))))
        elif m := re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", ln):
            flush()
            out.append(Block("img", m.group(1), path=(path.parent / m.group(2)).resolve()))
        elif ln.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            out.append(Block("table", rows=rows))
        elif re.match(r"^\s*[-*] ", ln):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append(re.sub(r"^\s*[-*] ", "", lines[i]))
                i += 1
            i -= 1
            out.append(Block("ul", items=items))
        elif re.match(r"^\d+\. ", ln):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                items.append(re.sub(r"^\d+\. ", "", lines[i]))
                i += 1
            i -= 1
            out.append(Block("ol", items=items))
        elif ln.strip() == "":
            flush()
        else:
            para.append(ln)
        i += 1
    flush()
    return out


def md_sections(path: Path) -> dict[str, list[Block]]:
    """Split a markdown file at level-2 headings: {heading: blocks below it}."""
    out: dict[str, list[Block]] = {}
    cur = ""
    for b in parse_md(path):
        if b.kind == "h" and b.level <= 2:
            cur = b.text
            out[cur] = []
        else:
            out.setdefault(cur, []).append(b)
    return out


def first_table(blocks: list[Block]) -> list[list[str]]:
    return next(b.rows for b in blocks if b.kind == "table" and b.rows)


# ------------------------------------------------------------------ code line numbers


def code_ref(file: str, name: str) -> str:
    """'file.py:LINE' of a top-level function / class or Class.method (from ast)."""
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
    parts = name.split(".")
    nodes: list[ast.AST] = list(tree.body)
    found = None
    for part in parts:
        found = next(
            (n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == part),
            None,
        )
        if found is None:
            raise KeyError(f"{file}: {name} not found")
        nodes = list(found.body)  # type: ignore[attr-defined]
    assert found is not None
    return f"{file}:{found.lineno}"


# ------------------------------------------------------------------ scenario facts


def scenario_facts() -> dict[str, str]:
    """Key numbers of the fixed scenario, parsed from docs/scenario/*.md."""
    walk = (SCEN / "walkthrough.md").read_text(encoding="utf-8")
    mm = (SCEN / "minimax.md").read_text(encoding="utf-8")
    f: dict[str, str] = {}
    f["tom_centroid"], f["tom_mode"] = re.search(
        r"## Tom \(HARD\).*?Centroid ([\d.]+), mode \*\*(\w+)\*\*", walk, re.S
    ).groups()  # type: ignore[union-attr]
    f["jerry_centroid"], f["jerry_mode"] = re.search(
        r"## Jerry \(HARD\).*?Centroid ([\d.]+), mode \*\*(\w+)\*\*", walk, re.S
    ).groups()  # type: ignore[union-attr]
    f["tom_action"] = re.search(r"## Tom \(HARD\): (\w+)", walk).group(1)  # type: ignore[union-attr]
    f["jerry_action"] = re.search(r"## Jerry \(HARD\): (\w+)", walk).group(1)  # type: ignore[union-attr]
    f["tom_values"] = re.search(r"Exact values: (.*?)\.\s", walk).group(1)  # type: ignore[union-attr]
    f["jerry_values"] = re.search(r"Values from Tom's view: (.*?)\.\s", walk).group(1)  # type: ignore[union-attr]
    f["tom_mm_nodes"] = re.search(r"depth 4, (\d+) nodes", walk).group(1)  # type: ignore[union-attr]
    f["jerry_mm_nodes"] = re.findall(r"depth 4, (\d+) nodes", walk)[1]
    f["plain_nodes"] = re.search(r"nodes, plain minimax depth 4 \| (\d+)", mm).group(1)  # type: ignore[union-attr]
    f["ab_nodes"] = re.search(r"nodes, alpha-beta depth 4 \| (\d+)", mm).group(1)  # type: ignore[union-attr]
    f["root_value"] = re.search(r"root value \(Tom's view\) \| \*\*(-?\d+)\*\*", mm).group(1)  # type: ignore[union-attr]
    return f


def bench_table() -> list[list[str]]:
    """The search benchmark table of docs/ALGORITHMS.md."""
    sec = md_sections(DOCS / "ALGORITHMS.md")
    return first_table(sec["Search benchmark"])


