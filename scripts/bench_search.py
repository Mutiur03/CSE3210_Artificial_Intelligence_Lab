"""Benchmark the search algorithms on seeded mazes and write the table into docs/ALGORITHMS.md.

Each maze: start = Jerry's start cell, goal = Tom's start cell (path distance >= 16).
Usage: python scripts/bench_search.py [--mazes 200] [--size 21]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from maze import generate_maze  # noqa: E402
from search import (  # noqa: E402
    SearchResult,
    astar,
    bfs,
    bidirectional_bfs,
    dfs,
    greedy_best_first,
    iddfs,
)

ALGORITHMS: dict[str, Callable[..., SearchResult]] = {
    "A*": astar,
    "Greedy best-first": greedy_best_first,
    "DFS": dfs,
    "Bidirectional BFS": bidirectional_bfs,
    "BFS": bfs,
    "IDDFS": iddfs,
}
DOC = ROOT / "docs" / "ALGORITHMS.md"
START, END = "<!-- BENCH:START -->", "<!-- BENCH:END -->"


def bench(n: int, size: int) -> str:
    """Run every algorithm on mazes with seeds 0..n-1; returns a Markdown table."""
    mazes = [generate_maze(seed, size) for seed in range(n)]
    lines = [f"Benchmark: {n} mazes, size {size}x{size}, seeds 0..{n - 1}, "
             "start = Jerry start, goal = Tom start.", "",
             "| Algorithm | Avg path length | Avg nodes expanded | Avg ms |",
             "|---|---:|---:|---:|"]
    for name, fn in ALGORITHMS.items():
        runs = [fn(m.adj, m.jerry_start, m.tom_start) for m in mazes]
        length = sum(len(r.path) - 1 for r in runs) / n
        nodes = sum(r.nodes_expanded for r in runs) / n
        ms = sum(r.ms for r in runs) / n
        lines.append(f"| {name} | {length:.2f} | {nodes:.1f} | {ms:.3f} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mazes", type=int, default=200)
    ap.add_argument("--size", type=int, default=21)
    args = ap.parse_args()
    table = bench(args.mazes, args.size)
    print(table)
    text = DOC.read_text(encoding="utf-8")
    block = f"{START}\n{table}\n{END}"
    DOC.write_text(re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, text,
                          flags=re.S), encoding="utf-8")
    print(f"\nwritten to {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
