"""Scan headless AI-vs-AI games for the four demo videos and write results/demo_seeds.json.

(a) Bruno saves Jerry : Jerry wins, Bruno bites Tom while Tom is within 3 steps of Jerry
    (Tom EASY: NORMAL and above flee Bruno and are never bitten, see docs/RESULTS.md E6).
(b) Minimax close chase: longest run (12-25 rounds) where BOTH sides pick their move by minimax.
(c) Fuzzy mode switch  : a 14-round window in which Tom's fuzzy mode takes the most values.
(d) Full game          : a Jerry win, 60-110 turns, Bruno woken at least once.
(e) Tom loses Jerry    : demo script only (no video): longest SWEEP run with Jerry out of sight.
Seeds 0..N-1, 21x21, Bruno on; (b)-(d) both sides HARD, (a) Tom EASY vs Jerry HARD. Deterministic.

Usage: python scripts/find_demo_seeds.py [--seeds 200]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402
from agents import make_agent  # noqa: E402
from game import JERRY, TOM, new_game, run_round  # noqa: E402
from maze import generate_maze  # noqa: E402

OUT = ROOT / "results" / "demo_seeds.json"
LEVEL = "HARD"
WINDOW = 14


def scan(job: tuple[int, str, str]) -> dict:
    """Play one game and keep per-round facts (turn index = state.turn before the round)."""
    seed, tom, jerry = job
    state = new_game(generate_maze(seed, C.DEFAULT_SIZE), True)
    agents = {TOM: make_agent(TOM, tom, seed * 2 + 1), JERRY: make_agent(JERRY, jerry, seed * 2)}
    last: dict[str, object] = {}

    def policy(role: str):  # type: ignore[no-untyped-def]
        def act(obs):  # type: ignore[no-untyped-def]
            last[role] = agents[role].act(obs)
            return last[role].action  # type: ignore[attr-defined]

        return act

    rows = []
    while state.winner is None:
        bites = state.bites
        turn = state.turn
        run_round(state, policy(JERRY), policy(TOM))
        d_tj = state.maze.dist(state.tom, state.jerry)
        rows.append(
            {
                "turn": turn,
                "tom_mode": last[TOM].mode,  # type: ignore[attr-defined]
                "tom_mm": last[TOM].algorithm.startswith("Minimax"),  # type: ignore[attr-defined]
                "jerry_mm": last[JERRY].algorithm.startswith("Minimax"),  # type: ignore[attr-defined]
                "dist": d_tj,
                "bite": state.bites > bites,
            }
        )
    return {
        "seed": seed,
        "tom": tom,
        "jerry": jerry,
        "winner": state.winner,
        "turns": min(state.turn, C.TURN_LIMIT),
        "activations": state.bruno.activations if state.bruno else 0,
        "rows": rows,
    }


def pick(bite_games: list[dict], games: list[dict]) -> dict:
    """Choose one seed per video."""
    out: dict = {}
    # (a) Bruno saves Jerry: smallest Tom-Jerry distance in the 3 rounds before a bite
    best = None
    for g in bite_games:
        if g["winner"] != JERRY:
            continue
        for i, r in enumerate(g["rows"]):
            if r["bite"]:
                near = min(x["dist"] for x in g["rows"][max(0, i - 3) : i + 1])
                if near <= 3 and (best is None or (near, g["turns"]) < best[0]):
                    best = ((near, g["turns"]), g["seed"], i)
    assert best is not None, "no Bruno-saves-Jerry game in the scanned seeds"
    _, seed, i = best
    g = next(x for x in bite_games if x["seed"] == seed)
    out["bruno_saves_jerry"] = {
        "tom": "EASY",
        "jerry": "HARD",
        "seed": seed,
        "from": max(0, i - 14),
        "to": min(g["turns"], i + 8),
        "note": f"Bruno bites Tom at turn {g['rows'][i]['turn']}",
    }
    # (b) longest run of 12-25 rounds where both sides use minimax (longer runs are stalemates)
    best = None
    for g in games:
        run = start = 0
        for i, r in enumerate(g["rows"] + [{"tom_mm": False, "jerry_mm": False}]):
            if r["tom_mm"] and r["jerry_mm"]:
                run += 1
            else:
                if 12 <= run <= 25 and (best is None or run > best[0]):
                    best = (run, g["seed"], i - run)
                run = 0
    assert best is not None, "no minimax chase found"
    n, seed, start = best
    g = next(x for x in games if x["seed"] == seed)
    out["minimax_chase"] = {
        "tom": LEVEL,
        "jerry": LEVEL,
        "seed": seed,
        "from": max(0, start - 3),
        "to": min(g["turns"], start + n + 3),
        "note": f"both sides search by minimax for {n} consecutive turns",
    }
    # (c) fuzzy mode switch: window with the most distinct Tom modes, then most switches
    best = None
    for g in games:
        modes = [r["tom_mode"] for r in g["rows"]]
        for s in range(0, max(1, len(modes) - WINDOW)):
            w = modes[s : s + WINDOW]
            key = (len(set(w)), sum(a != b for a, b in zip(w, w[1:], strict=False)))
            if best is None or key > best[0]:
                best = (key, g["seed"], s)
    assert best is not None
    key, seed, s = best
    g = next(x for x in games if x["seed"] == seed)
    seq = " -> ".join(dict.fromkeys(r["tom_mode"] for r in g["rows"][s : s + WINDOW]))
    out["fuzzy_switch"] = {
        "tom": LEVEL,
        "jerry": LEVEL,
        "seed": seed,
        "from": s,
        "to": min(g["turns"], s + WINDOW),
        "note": f"Tom's fuzzy mode: {seq}",
    }
    # (d) full game: first Jerry win of 60-110 turns with Bruno woken
    full = next(
        g
        for g in games
        if g["winner"] == JERRY and 60 <= g["turns"] <= 110 and g["activations"] > 0
    )
    out["full_game"] = {
        "tom": LEVEL,
        "jerry": LEVEL,
        "seed": full["seed"],
        "from": 0,
        "to": full["turns"],
        "note": f"Jerry escapes after {full['turns']} turns, Bruno woken {full['activations']}x",
    }
    # (e) demo only (no video): Tom loses Jerry = longest run of SWEEP rounds with Jerry beyond vision
    best = None
    for g in games:
        run = 0
        for i, r in enumerate(g["rows"] + [{"tom_mode": "", "dist": 0}]):
            if r["tom_mode"] == "SWEEP" and r["dist"] > C.VISION_RADIUS:
                run += 1
            else:
                if run and (best is None or run > best[0]):
                    best = (run, g["seed"], i - run)
                run = 0
    assert best is not None
    n, seed, start = best
    out["tom_loses_jerry"] = {
        "tom": LEVEL,
        "jerry": LEVEL,
        "seed": seed,
        "from": start,
        "to": start + n,
        "video": False,
        "note": f"Tom sweeps for {n} consecutive turns with Jerry outside his vision",
    }
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, default=200)
    args = p.parse_args()
    with ProcessPoolExecutor(max(1, (os.cpu_count() or 2) - 1)) as pool:
        games = list(pool.map(scan, [(s, LEVEL, LEVEL) for s in range(args.seeds)], chunksize=4))
        bite_games = list(
            pool.map(scan, [(s, "EASY", LEVEL) for s in range(args.seeds)], chunksize=4)
        )
    picked = pick(bite_games, games)
    picked["setup"] = {"size": C.DEFAULT_SIZE, "bruno": True, "scanned": args.seeds}
    OUT.write_text(json.dumps(picked, indent=1), encoding="utf-8")
    for k, v in picked.items():
        print(k, v)


if __name__ == "__main__":
    main()
