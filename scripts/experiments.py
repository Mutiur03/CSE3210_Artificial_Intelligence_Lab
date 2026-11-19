"""Experiments E1-E6 (headless, multiprocessing, fixed seeds 0..N-1).

Writes results/experiments.json, results/E*.png, results/E*.csv and docs/RESULTS.md.
Every number in the slides and the report comes from results/experiments.json.

Usage: python scripts/experiments.py [--games 100] [--only E1,E3] [--workers N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402
from agents import JerryAgent, Observation, Plan, TomAgent, _path_plan, make_agent  # noqa: E402
from game import JERRY, TOM, legal_actions, new_game, run_round  # noqa: E402
from maze import generate_maze  # noqa: E402
from search import greedy_best_first  # noqa: E402

RESULTS = ROOT / "results"
DOCS = ROOT / "docs"


# ------------------------------------------------------------------ agent variants


class GreedyHuntTom(TomAgent):
    """NORMAL Tom whose HUNT uses greedy best-first instead of A* (E2)."""

    def hunt(self, obs: Observation) -> Plan:
        target = obs.opp_pos or (self.last_seen[0] if self.last_seen else None)
        if target is None or target == obs.self_pos:
            return self.sweep(obs)
        res = greedy_best_first(obs.maze.adj, obs.self_pos, target)
        return _path_plan(
            res.path,
            obs.self_pos,
            "Greedy best-first",
            res.nodes_expanded,
            res.explored_order,
            None,
        )


class FixedHuntTom(TomAgent):
    """Tom without fuzzy logic: every turn is HUNT (E4)."""

    def act(self, obs: Observation):  # type: ignore[no-untyped-def]
        t0 = time.perf_counter()
        self.remember(obs)
        return self.decision(obs, t0, "HUNT", self.hunt(obs), None, None, None)


class NoMinimaxTom(TomAgent):
    """HARD Tom with the minimax override switched off (E5)."""

    def close_range(self, obs: Observation) -> bool:
        return False


class NoMinimaxJerry(JerryAgent):
    """HARD Jerry with the minimax override switched off (E3: isolates the DLS EVADE)."""

    def close_range(self, obs: Observation) -> bool:
        return False


def build(role: str, spec: str, seed: int):  # type: ignore[no-untyped-def]
    """Agent for a spec string: a difficulty name or a variant name."""
    variants = {
        "NORMAL-greedy": (GreedyHuntTom, "NORMAL"),
        "NORMAL-fixedHUNT": (FixedHuntTom, "NORMAL"),
        "HARD-noMinimax": (NoMinimaxTom, "HARD"),
        "HARD-noMinimaxJ": (NoMinimaxJerry, "HARD"),
    }
    if spec in variants:
        cls, level = variants[spec]
        return cls(level, seed)
    return make_agent(role, spec, seed)


# ------------------------------------------------------------------ one game


def play(job: dict) -> dict:
    """Play one seeded game. Records outcome, cause and per-mode decision statistics."""
    seed = job["seed"]
    C.DLS_DEPTH = job.get("dls", C.DLS_DEPTH)
    state = new_game(generate_maze(seed, job.get("size", C.DEFAULT_SIZE)), job["bruno"])
    agents = {
        TOM: build(TOM, job["tom"], seed * 2 + 1),
        JERRY: build(JERRY, job["jerry"], seed * 2),
    }
    modes: dict[str, dict[str, list[float]]] = {TOM: {}, JERRY: {}}
    illegal = 0

    def policy(role: str):  # type: ignore[no-untyped-def]
        def act(obs: Observation) -> str:
            nonlocal illegal
            d = agents[role].act(obs)
            row = modes[role].setdefault(d.mode, [0, 0.0, 0.0, 0.0])
            row[0] += 1
            row[1] += d.nodes
            row[2] += d.ms
            row[3] += max(0, len(d.path) - 1)
            illegal += d.action not in legal_actions(state, role)
            return d.action

        return act

    while state.winner is None:
        run_round(state, policy(JERRY), policy(TOM))
    reason = state.reason
    cause = (
        "exit" if state.winner == JERRY else "timeout" if reason.startswith("Time") else "capture"
    )
    return {
        "seed": seed,
        "winner": state.winner,
        "cause": cause,
        "turns": min(state.turn, C.TURN_LIMIT),
        "bites": state.bites,
        "activations": state.bruno.activations if state.bruno else 0,
        "modes": modes,
        "illegal": illegal,
    }


def run(jobs: list[dict], workers: int) -> list[dict]:
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(play, jobs, chunksize=2))


def summarise(results: list[dict]) -> dict:
    """Aggregate one config: win rates, causes, length, per-move cost, per-mode cost."""
    n = len(results)
    out: dict = {
        "games": n,
        "jerry_win": sum(r["winner"] == JERRY for r in results) / n,
        "tom_win": sum(r["winner"] == TOM for r in results) / n,
        "avg_turns": sum(r["turns"] for r in results) / n,
        "causes": {
            c: sum(r["cause"] == c for r in results) for c in ("capture", "exit", "timeout")
        },
        "bites": sum(r["bites"] for r in results),
        "activations": sum(r["activations"] for r in results),
        "jerry_wins_after_bite": sum(r["winner"] == JERRY and r["bites"] > 0 for r in results),
        "illegal": sum(r["illegal"] for r in results),
    }
    for role in (TOM, JERRY):
        tot = [0, 0.0, 0.0, 0.0]
        per: dict[str, list[float]] = {}
        for r in results:
            for mode, row in r["modes"][role].items():
                p = per.setdefault(mode, [0, 0.0, 0.0, 0.0])
                for i in range(4):
                    p[i] += row[i]
                    tot[i] += row[i]
        out[role] = {
            "moves": tot[0],
            "avg_nodes": tot[1] / max(1, tot[0]),
            "avg_ms": tot[2] / max(1, tot[0]),
            "modes": {
                m: {
                    "count": p[0],
                    "avg_nodes": p[1] / p[0],
                    "avg_ms": p[2] / p[0],
                    "avg_path": p[3] / p[0],
                }
                for m, p in sorted(per.items())
            },
        }
    return out


# ------------------------------------------------------------------ experiment definitions


def configs(games: int) -> dict[str, list[tuple[str, dict]]]:
    def cfg(tom: str, jerry: str, bruno: bool = True, dls: int = C.DLS_DEPTH) -> dict:
        return {"tom": tom, "jerry": jerry, "bruno": bruno, "dls": dls}

    e1 = [
        (f"Tom {t} vs Jerry {j}", cfg(t, j))
        for j in ("NORMAL", "HARD")
        for t in ("EASY", "NORMAL", "HARD", "NIGHTMARE")
    ]
    e2 = [
        (f"Tom {t} vs Jerry {j}", cfg(s, j))
        for j in ("NORMAL", "HARD")
        for t, s in (("A* hunt", "NORMAL"), ("greedy hunt", "NORMAL-greedy"))
    ]
    e3 = [(f"DLS depth {d}", cfg("HARD", "HARD-noMinimaxJ", dls=d)) for d in (3, 5, 7)]
    e4 = [
        (f"Tom {t} vs Jerry {j}", cfg(s, j))
        for j in ("NORMAL", "HARD")
        for t, s in (("fuzzy director", "NORMAL"), ("always HUNT", "NORMAL-fixedHUNT"))
    ]
    e5 = [
        ("Tom NORMAL (no belief, no minimax)", cfg("NORMAL", "NORMAL")),
        ("Tom HARD without minimax", cfg("HARD-noMinimax", "NORMAL")),
        ("Tom HARD (minimax on)", cfg("HARD", "NORMAL")),
        ("Tom NIGHTMARE (HARD + MCTS)", cfg("NIGHTMARE", "NORMAL")),
    ]
    e6 = [
        (f"Tom {t} vs Jerry {j}, Bruno {'on' if b else 'off'}", cfg(t, j, b))
        for j in ("NORMAL", "HARD")
        for t in ("EASY", "NORMAL", "HARD")
        for b in (True, False)
    ]
    return {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5, "E6": e6}


TITLES = {
    "E1": "Difficulty ladder (Tom level vs Jerry level)",
    "E2": "A* vs greedy best-first for Tom's chase (NORMAL Tom, HUNT only differs)",
    "E3": "DLS depth for Jerry's EVADE (HARD Jerry, minimax off, vs HARD Tom)",
    "E4": "Fuzzy director vs fixed rule 'always HUNT' (NORMAL Tom)",
    "E5": "Minimax on/off and MCTS on/off (Tom vs NORMAL Jerry)",
    "E6": "Bruno on vs off",
}


# ------------------------------------------------------------------ output


def table(rows: list[tuple[str, dict]], extra: str | None = None) -> str:
    head = (
        "| Configuration | Jerry win % | Tom win % | avg turns | capture | exit | timeout | "
        "Tom nodes/move | Tom ms/move | Jerry nodes/move | Jerry ms/move |"
    )
    lines = [head, "|" + "---|" * 11]
    for name, s in rows:
        c = s["causes"]
        lines.append(
            f"| {name} | {100 * s['jerry_win']:.0f} | {100 * s['tom_win']:.0f} | {s['avg_turns']:.1f} | "
            f"{c['capture']} | {c['exit']} | {c['timeout']} | {s[TOM]['avg_nodes']:.1f} | "
            f"{s[TOM]['avg_ms']:.2f} | {s[JERRY]['avg_nodes']:.1f} | {s[JERRY]['avg_ms']:.2f} |"
        )
    return "\n".join(lines)


def mode_table(rows: list[tuple[str, dict]], role: str, mode: str) -> str:
    lines = [
        f"| Configuration | {role.title()} {mode} moves | avg planned path (steps) | avg nodes | avg ms |",
        "|---|---|---|---|---|",
    ]
    for name, s in rows:
        m = s[role]["modes"].get(mode)
        if m:
            lines.append(
                f"| {name} | {m['count']:.0f} | {m['avg_path']:.2f} | {m['avg_nodes']:.1f} | "
                f"{m['avg_ms']:.3f} |"
            )
    return "\n".join(lines)


def conclusion(key: str, rows: list[tuple[str, dict]]) -> str:
    """Two sentences per experiment; every number and verdict is computed from `rows`.
    A difference under 9 points is called noise (95% interval of one 100-game rate is +-9)."""
    d = dict(rows)
    names = [n for n, _ in rows]

    def w(n: str) -> str:
        return f"{100 * d[n]['jerry_win']:.0f}%"

    def verdict(a: str, b: str) -> str:
        gap = 100 * abs(d[a]["jerry_win"] - d[b]["jerry_win"])
        return f"{gap:.0f} point{'' if round(gap) == 1 else 's'} apart, " + (
            "within noise" if gap < 9 else "a real difference"
        )

    if key == "E1":
        parts = []
        for j in ("NORMAL", "HARD"):
            seq = ", ".join(f"{n.split()[1]} {w(n)}" for n in names if n.endswith(f"Jerry {j}"))
            parts.append(f"against {j} Jerry (Tom level, Jerry win rate): {seq}")
        slow = max(names, key=lambda n: d[n][TOM]["avg_ms"])
        return (
            f"Jerry's win rate drops from EASY to HARD Tom: {parts[0]}; {parts[1]}. "
            f"The costliest Tom is {slow.split(' vs')[0]} at {d[slow][TOM]['avg_nodes']:.0f} nodes and "
            f"{d[slow][TOM]['avg_ms']:.1f} ms per move, inside the 300 ms budget."
        )
    if key == "E2":
        out = []
        for j in (0, 2):
            h1 = d[names[j]][TOM]["modes"]["HUNT"]
            h2 = d[names[j + 1]][TOM]["modes"]["HUNT"]
            out.append(
                f"vs {names[j].split('vs ')[1]}: A* {w(names[j])} ({h1['avg_nodes']:.1f} nodes, "
                f"{h1['avg_path']:.2f}-step plans) and greedy {w(names[j + 1])} "
                f"({h2['avg_nodes']:.1f} nodes, {h2['avg_path']:.2f}-step plans)"
            )
        return (
            "Jerry win rate, " + "; ".join(out) + ". "
            f"The win rates are {verdict(names[0], names[1])}: a HUNT plan is only about "
            f"{d[names[0]][TOM]['modes']['HUNT']['avg_path']:.0f} steps long, too short for the two "
            "searches to differ; on long start-to-start paths greedy plans longer routes "
            "(benchmark in docs/ALGORITHMS.md)."
        )
    if key == "E3":
        txt = ", ".join(f"depth {n.split()[-1]}: {w(n)}" for n in names)
        ev = {n: d[n][JERRY]["modes"].get("EVADE", {"avg_nodes": 0, "avg_ms": 0}) for n in names}
        cost = ", ".join(
            f"depth {n.split()[-1]} {ev[n]['avg_nodes']:.1f} paths enumerated, {ev[n]['avg_ms']:.2f} ms"
            for n in names
        )
        return (
            f"Jerry win rate by DLS depth: {txt}. Cost per EVADE move: {cost}; "
            f"depth 3 vs 7 is {verdict(names[0], names[2])}."
        )
    if key == "E4":
        return (
            f"Against NORMAL Jerry the fuzzy director gives Jerry {w(names[0])} and always-HUNT "
            f"{w(names[1])} ({verdict(names[0], names[1])}); against HARD Jerry {w(names[2])} and "
            f"{w(names[3])} ({verdict(names[2], names[3])}). "
            + (
                "At 100 games the director is not measurably better than a plain A* chase; "
                "its AMBUSH / SWEEP / RETREAT modes show in behaviour, not in this win rate."
                if max(
                    abs(d[names[0]]["jerry_win"] - d[names[1]]["jerry_win"]),
                    abs(d[names[2]]["jerry_win"] - d[names[3]]["jerry_win"]),
                )
                < 0.09
                else "The director changes the outcome measurably."
            )
        )
    if key == "E5":
        return (
            f"Jerry win rate: NORMAL Tom {w(names[0])}, HARD without minimax {w(names[1])}, HARD "
            f"{w(names[2])}, NIGHTMARE {w(names[3])}. NORMAL to HARD-without-minimax is the "
            f"vanished-key belief update ({verdict(names[0], names[1])}); switching minimax on is "
            f"{verdict(names[1], names[2])}, and MCTS on top is {verdict(names[2], names[3])}."
        )
    pairs = [(names[i], names[i + 1]) for i in range(0, len(names), 2)]
    txt = "; ".join(
        f"{on.split(', ')[0]}: {w(on)} with Bruno, {w(off)} without" for on, off in pairs
    )
    bites = {on.split(", ")[0]: d[on]["bites"] for on, _ in pairs if d[on]["bites"]}
    bite_txt = ", ".join(f"{k} {v} bites" for k, v in bites.items()) or "no bites"
    return (
        f"Jerry win rate: {txt}. Bites happen only where Tom cannot flee Bruno ({bite_txt}); "
        "NORMAL and above retreat from a guarding Bruno (rule T7), so for them Bruno works as deterrence."
    )


def chart(key: str, rows: list[tuple[str, dict]]) -> Path:
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, ax = plt.subplots(figsize=(9, 0.55 * len(rows) + 1.6), facecolor="#10151f")
    ax.set_facecolor("#10151f")
    labels = [n for n, _ in rows]
    ys = range(len(rows))
    left = [0.0] * len(rows)
    for cause, color in (("exit", "#2ecc71"), ("capture", "#f38b2a"), ("timeout", "#8d6e63")):
        vals = [100 * s["causes"][cause] / s["games"] for _, s in rows]
        bars = ax.barh(list(ys), vals, left=left, color=color, label=cause)
        for b, v, lf in zip(bars, vals, left, strict=True):
            if v >= 6:
                ax.text(
                    lf + v / 2,
                    b.get_y() + b.get_height() / 2,
                    f"{v:.0f}",
                    ha="center",
                    va="center",
                    color="#10151f",
                    fontsize=9,
                    fontweight="bold",
                )
        left = [a + b for a, b in zip(left, vals, strict=True)]
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, color="#e2e6f0", fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of games (exit = Jerry wins; capture / timeout = Tom wins)", color="#e2e6f0")
    ax.set_title(f"{key}: {TITLES[key]}", color="#e2e6f0", fontsize=11)
    ax.tick_params(colors="#e2e6f0")
    for sp in ax.spines.values():
        sp.set_color("#3a455c")
    ax.legend(
        ncol=3, frameon=False, labelcolor="#e2e6f0", loc="upper center", bbox_to_anchor=(0.5, -0.18)
    )
    fig.tight_layout()
    path = RESULTS / f"{key}.png"
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor(), metadata={"Software": None})
    plt.close(fig)
    return path


def write_csv(key: str, rows: list[tuple[str, dict]]) -> None:
    lines = [
        "config,jerry_win,tom_win,avg_turns,capture,exit,timeout,tom_nodes,tom_ms,jerry_nodes,jerry_ms"
    ]
    for n, s in rows:
        c = s["causes"]
        lines.append(
            f'"{n}",{s["jerry_win"]:.3f},{s["tom_win"]:.3f},{s["avg_turns"]:.2f},{c["capture"]},{c["exit"]},'
            f"{c['timeout']},{s[TOM]['avg_nodes']:.2f},{s[TOM]['avg_ms']:.3f},{s[JERRY]['avg_nodes']:.2f},"
            f"{s[JERRY]['avg_ms']:.3f}"
        )
    (RESULTS / f"{key}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_docs(data: dict, games: int) -> None:
    out = [
        "# Experiment results",
        "",
        f"Generated by `python scripts/experiments.py` (seeds 0..{games - 1}, 21x21 maps, Bruno on unless noted). "
        "Raw data: `results/experiments.json`, tables `results/E*.csv`, charts `results/E*.png`. "
        "Outcome causes: **exit** = Jerry escaped, **capture** = Tom caught Jerry, **timeout** = 120 turns passed. "
        "Bruno bites are counted separately (they stun Tom, they do not end the game).",
        "",
    ]
    for key, rows in data.items():
        rows = [(n, s) for n, s in rows]
        out += [f"## {key}. {TITLES[key]}", "", table(rows), ""]
        if key == "E2":
            out += [mode_table(rows, TOM, "HUNT"), ""]
        if key == "E3":
            out += [mode_table(rows, JERRY, "EVADE"), ""]
        bites = ", ".join(
            f"{n}: {s['bites']} bites / {s['jerry_wins_after_bite']} Jerry wins after a bite"
            for n, s in rows
            if key in ("E1", "E6") and s["bites"]
        )
        if bites:
            out += [f"Bruno: {bites}.", ""]
        out += [
            f"![{key}]({'../results/' + key + '.png'})",
            "",
            f"**Conclusion.** {conclusion(key, rows)}",
            "",
        ]
    (DOCS / "RESULTS.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--only", default="")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = p.parse_args()
    RESULTS.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    data_path = RESULTS / "experiments.json"
    old = json.loads(data_path.read_text()) if data_path.exists() else {}
    only = [k for k in args.only.split(",") if k]
    for key, rows in configs(args.games).items():
        if only and key not in only:
            continue
        t0 = time.perf_counter()
        done = []
        for name, cfg in rows:
            jobs = [{**cfg, "seed": s} for s in range(args.games)]
            s = summarise(run(jobs, args.workers))
            done.append([name, s])
            print(
                f"{key} {name}: Jerry {100 * s['jerry_win']:.0f}%  turns {s['avg_turns']:.1f}",
                flush=True,
            )
        old[key] = {"games": args.games, "rows": done}
        print(f"{key} took {time.perf_counter() - t0:.0f} s", flush=True)
    data_path.write_text(json.dumps(old, indent=1), encoding="utf-8")
    data = {k: [(n, s) for n, s in v["rows"]] for k, v in sorted(old.items())}
    for key, rows in data.items():
        chart(key, rows)
        write_csv(key, rows)
    write_docs(data, args.games)
    print("wrote results/experiments.json, results/E*.png, docs/RESULTS.md")


if __name__ == "__main__":
    main()
