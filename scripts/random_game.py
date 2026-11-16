"""Random Jerry vs random Tom, headless. Checks invariants every round.

Usage: python scripts/random_game.py [--games 200] [--size 21] [--no-bruno]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import RandomAgent  # noqa: E402
from game import JERRY, TOM, invariant_errors, new_game, run_round  # noqa: E402
from maze import generate_maze  # noqa: E402


def play_games(n: int, size: int = 21, bruno: bool = True) -> dict:
    """Play `n` seeded games (seeds 0..n-1). Returns win counts, lengths, errors."""
    summary: dict = {"games": n, "jerry_wins": 0, "tom_wins": 0, "turns": [], "reasons": {},
                     "bites": 0, "activations": 0, "errors": []}
    for seed in range(n):
        state = new_game(generate_maze(seed, size), bruno)
        jerry, tom = RandomAgent(seed * 2), RandomAgent(seed * 2 + 1)
        while state.winner is None:
            run_round(state, lambda o: jerry.act(o).action, lambda o: tom.act(o).action)
            summary["errors"] += [f"seed {seed} turn {state.turn}: {e}"
                                  for e in invariant_errors(state)]
        summary["jerry_wins" if state.winner == JERRY else "tom_wins"] += 1
        summary["turns"].append(state.turn)
        summary["reasons"][state.reason] = summary["reasons"].get(state.reason, 0) + 1
        summary["bites"] += state.bites
        summary["activations"] += state.bruno.activations if state.bruno else 0
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--size", type=int, default=21)
    p.add_argument("--no-bruno", action="store_true")
    args = p.parse_args()
    t0 = time.perf_counter()
    s = play_games(args.games, args.size, not args.no_bruno)
    n = s["games"]
    print(f"{n} games, size {args.size}, {time.perf_counter() - t0:.1f}s")
    print(f"{JERRY} wins: {s['jerry_wins']}  {TOM} wins: {s['tom_wins']}")
    print(f"average length: {sum(s['turns']) / n:.1f} turns")
    for reason, count in sorted(s["reasons"].items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {reason}")
    print(f"Bruno activations: {s['activations']}  bites: {s['bites']}")
    print(f"invariant errors: {len(s['errors'])}")
    for e in s["errors"][:10]:
        print("  ", e)


if __name__ == "__main__":
    main()
