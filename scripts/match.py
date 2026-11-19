"""Headless AI-vs-AI matches with fixed seeds. Prints win rates and timing.

Usage: python scripts/match.py --tom hard --jerry normal --games 100 --size 21
       python scripts/match.py --ladder --games 100   (every Tom level vs one Jerry)
Seeds are 0..games-1, so a run is reproducible. Games run in parallel processes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C  # noqa: E402
from agents import BUDGET_MS, DIFFICULTIES, make_agent  # noqa: E402
from game import JERRY, TOM, invariant_errors, legal_actions, new_game, run_round  # noqa: E402
from maze import generate_maze  # noqa: E402


def play_one(args: tuple[int, str, str, int, bool]) -> dict:
    """Play one seeded game. Records every decision's time and legality."""
    seed, tom_level, jerry_level, size, bruno = args
    state = new_game(generate_maze(seed, size), bruno)
    agents = {TOM: make_agent(TOM, tom_level, seed * 2 + 1),
              JERRY: make_agent(JERRY, jerry_level, seed * 2)}
    stats = {TOM: [], JERRY: []}
    illegal: list[str] = []
    errors: list[str] = []
    nodes = {TOM: 0, JERRY: 0}

    def policy(role: str):
        def act(obs):  # type: ignore[no-untyped-def]
            d = agents[role].act(obs)
            stats[role].append(d.ms)
            nodes[role] += d.nodes
            if d.action not in legal_actions(state, role):
                illegal.append(f"seed {seed} turn {obs.turn} {role} {d.action}")
            return d.action
        return act

    while state.winner is None:
        run_round(state, policy(JERRY), policy(TOM))
        errors += invariant_errors(state)
    return {"seed": seed, "winner": state.winner, "reason": state.reason, "turns": state.turn,
            "ms": stats, "nodes": nodes, "illegal": illegal, "errors": errors,
            "bites": state.bites, "activations": state.bruno.activations if state.bruno else 0}


def run_match(tom: str, jerry: str, games: int, size: int = C.DEFAULT_SIZE, bruno: bool = True,
              workers: int | None = None, first_seed: int = 0) -> dict:
    """Play `games` seeded games in parallel and summarise them."""
    jobs = [(s, tom, jerry, size, bruno) for s in range(first_seed, first_seed + games)]
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    if workers == 1:
        results = [play_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(play_one, jobs))
    out = {"tom": tom, "jerry": jerry, "games": games, "results": results,
           "tom_wins": sum(r["winner"] == TOM for r in results),
           "jerry_wins": sum(r["winner"] == JERRY for r in results)}
    for role, level in ((TOM, tom), (JERRY, jerry)):
        times = [t for r in results for t in r["ms"][role]]
        budget = BUDGET_MS.get(level)
        out[role] = {"moves": len(times), "avg_ms": sum(times) / max(1, len(times)),
                     "max_ms": max(times, default=0.0), "budget": budget,
                     "over": sum(t > budget * 1.2 for t in times) if budget else 0}
    return out


def report(m: dict) -> str:
    n = m["games"]
    res = m["results"]
    reasons: dict[str, int] = {}
    for r in res:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    lines = [f"Tom {m['tom']} vs Jerry {m['jerry']}: {n} games",
             f"  Tom wins {m['tom_wins']} ({100 * m['tom_wins'] / n:.0f}%)   "
             f"Jerry wins {m['jerry_wins']} ({100 * m['jerry_wins'] / n:.0f}%)   "
             f"avg length {sum(r['turns'] for r in res) / n:.1f} turns"]
    lines += [f"    {c:4d}  {why}" for why, c in sorted(reasons.items(), key=lambda kv: -kv[1])]
    for role in (TOM, JERRY):
        s = m[role]
        budget = f"budget {s['budget']} ms, over +20%: {s['over']}" if s["budget"] else "no budget"
        lines.append(f"  {role:5s} moves {s['moves']:6d}  avg {s['avg_ms']:6.2f} ms  "
                     f"max {s['max_ms']:7.2f} ms  ({budget})")
    illegal = sum(len(r["illegal"]) for r in res)
    errors = sum(len(r["errors"]) for r in res)
    lines.append(f"  illegal actions: {illegal}   invariant errors: {errors}   "
                 f"bites: {sum(r['bites'] for r in res)}   "
                 f"Bruno activations: {sum(r['activations'] for r in res)}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    levels = [d.lower() for d in DIFFICULTIES]
    p.add_argument("--tom", default="hard", choices=levels)
    p.add_argument("--jerry", default="normal", choices=levels)
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--size", type=int, default=C.DEFAULT_SIZE, choices=C.MAP_SIZES)
    p.add_argument("--no-bruno", action="store_true")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--ladder", action="store_true", help="every Tom level vs --jerry")
    args = p.parse_args()
    toms = levels if args.ladder else [args.tom]
    for tom in toms:
        t0 = time.perf_counter()
        m = run_match(tom.upper(), args.jerry.upper(), args.games, args.size,
                      not args.no_bruno, args.workers)
        print(report(m))
        print(f"  ({time.perf_counter() - t0:.1f} s wall)")


if __name__ == "__main__":
    main()
