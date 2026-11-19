"""Draw docs/diagrams/architecture.png and bruno_fsm.png (matplotlib) for the report.

Constants on the Bruno diagram come from config.py. Usage: python scripts/diagrams.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagrams"


def box(ax, x, y, w, h, text, edge="#2c6fb0", fill="#eef4fb", size=9):  # type: ignore[no-untyped-def]
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fill, ec=edge, lw=1.6
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size)


def arrow(ax, p, q, text="", color="#444", rad=0.0, off=(0, 0), size=8):  # type: ignore[no-untyped-def]
    ax.add_patch(
        FancyArrowPatch(
            p,
            q,
            arrowstyle="-|>",
            mutation_scale=14,
            color=color,
            lw=1.6,
            connectionstyle=f"arc3,rad={rad}",
        )
    )
    if text:
        ax.text(
            (p[0] + q[0]) / 2 + off[0],
            (p[1] + q[1]) / 2 + off[1],
            text,
            ha="center",
            va="center",
            fontsize=size,
            color="#222",
            bbox={"fc": "white", "ec": "none", "pad": 1},
        )


def architecture() -> None:
    fig, ax = plt.subplots(figsize=(9, 5.6))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    ax.text(0.1, 5.95, "Engine: pure Python, no pygame, headless", fontsize=10, weight="bold")
    mods = [
        ("maze.py\nDFS carve, loops,\nvalidation", 0.1, 4.4),
        ("game.py\nrules, fog, Bruno FSM,\nobservations", 2.45, 4.4),
        ("search.py\nA*, greedy, DFS, DLS,\nbidirectional, IDDFS", 4.8, 4.4),
        ("fuzzy.py\nMamdani engine,\nTom + Jerry controllers", 0.1, 3.2),
        ("minimax.py\nplain + alpha-beta", 2.45, 3.2),
        ("mcts.py\ninformation-set UCT", 4.8, 3.2),
    ]
    for t, x, y in mods:
        box(ax, x, y, 2.2, 1.0, t)
    box(
        ax,
        0.1,
        1.85,
        6.9,
        1.05,
        "agents.py   Decision, Agent, TomAgent, JerryAgent, difficulties\n"
        "reads an Observation only: fuzzy picks the mode,\nthe mode picks the algorithm",
        edge="#b8860b",
        fill="#fff8e1",
    )
    for x in (1.2, 3.55, 5.9):
        arrow(ax, (x, 3.2), (x, 2.9))
    ax.text(7.5, 5.95, "Pygame layer", fontsize=10, weight="bold")
    for i, t in enumerate(
        [
            "main.py  menu, loop, input",
            "ui.py  board, panel, overlays",
            "demo.py  algorithm demo (F2)",
            "record.py  frames -> mp4",
        ]
    ):
        box(ax, 7.4, 4.75 - i * 0.95, 2.9, 0.75, t, edge="#2e8b57", fill="#eefaf1", size=8)
    arrow(ax, (7.0, 2.4), (7.4, 2.4), "")
    ax.text(7.2, 2.15, "Decision", ha="center", fontsize=8)
    ax.text(0.1, 1.45, "Offline tools (same engine)", fontsize=10, weight="bold")
    box(
        ax,
        0.1,
        0.25,
        10.2,
        1.05,
        "scenario.py  fixed position, trace reports      scripts/  experiments, find_demo_seeds, build_slides,\n"
        "build_report, check_consistency, bench_search, match      tests/  pytest suite (headless)",
        edge="#888",
        fill="#f4f4f4",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "architecture.png", dpi=150, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def bruno_fsm() -> None:
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 6)
    ax.axis("off")
    pos = {"SLEEP": (0.5, 4.2), "GUARD": (6.5, 4.2), "CHASE_CAT": (6.5, 0.8), "TIRED": (0.5, 0.8)}
    col = {
        "SLEEP": ("#2c6fb0", "#eef4fb"),
        "GUARD": ("#2e8b57", "#eefaf1"),
        "CHASE_CAT": ("#d9741a", "#fff1e3"),
        "TIRED": ("#777", "#f2f2f2"),
    }
    for n, (x, y) in pos.items():
        box(ax, x, y, 3.0, 1.0, n, edge=col[n][0], fill=col[n][1], size=12)
    arrow(
        ax,
        (3.5, 4.7),
        (6.5, 4.7),
        f"Jerry steps on the kennel\n(activations < {C.BRUNO_MAX_ACTIVATIONS}): guard timer {C.BRUNO_GUARD_TURNS}",
        off=(0, 0.55),
    )
    arrow(
        ax,
        (7.6, 4.2),
        (7.6, 1.8),
        f"Tom within {C.BRUNO_CHASE_TRIGGER_DIST}\nand not stunned",
        off=(-0.95, 0),
    )
    arrow(
        ax,
        (8.8, 1.8),
        (8.8, 4.2),
        f"bite (Tom stun {C.BRUNO_BITE_STUN}, cooldown {C.BRUNO_BITE_COOLDOWN})\nor Tom farther than {C.BRUNO_CHASE_GIVEUP_DIST}",
        off=(1.45, 0),
    )
    arrow(
        ax,
        (6.5, 1.3),
        (3.5, 1.3),
        f"guard timer 0 -> tired timer {C.BRUNO_TIRED_TURNS}",
        off=(0, -0.45),
    )
    arrow(ax, (2.0, 1.8), (2.0, 4.2), "at the kennel and tired timer 0", off=(-1.05, 0))
    arrow(
        ax,
        (6.5, 4.3),
        (3.5, 1.6),
        f"guard timer 0 (after {C.BRUNO_GUARD_TURNS} rounds)",
        off=(-0.1, 0.35),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "bruno_fsm.png", dpi=150, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def main() -> None:
    architecture()
    bruno_fsm()
    print(f"wrote {OUT}/architecture.png, bruno_fsm.png")


if __name__ == "__main__":
    main()
