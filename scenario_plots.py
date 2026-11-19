"""Matplotlib figures for the scenario report (maze, fuzzy curves, search trees, Bruno strip).

Light background, large fonts: every figure is sized so it stays readable when
printed on A4 (portrait 6.5 in wide, landscape 9.5 in). Saved without a
version / date stamp, so the same data always gives byte-identical files.
No pygame here.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from fuzzy import FuzzyVar  # noqa: E402
from maze import Maze  # noqa: E402
from search import Cell  # noqa: E402

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
                     "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
                     "legend.fontsize": 9, "figure.facecolor": "white"})

FLOOR, WALL = "#eef1f7", "#2b3a55"
TOM_C, JERRY_C, BRUNO_C, KENNEL_C = "#f38b2a", "#9a9aa6", "#6d4c41", "#bfa29a"
KEY_C, EXIT_LOCKED, EXIT_OPEN = "#ffd23f", "#c0392b", "#2ecc71"
PV_C, PRUNED_C = "#1b9e4b", "#d9d9d9"
SET_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]


def save(fig: Figure, path: Path) -> None:
    """Write `fig` as PNG with no Software / date metadata (reproducible bytes)."""
    fig.savefig(path, dpi=200, metadata={"Software": None}, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


# ------------------------------------------------------------------ board


def _center(cell: Cell, off: tuple[float, float] = (0, 0)) -> tuple[float, float]:
    return cell[1] + 0.5 + off[0], cell[0] + 0.5 + off[1]


def draw_board(ax: Axes, maze: Maze, *, tom: Cell | None = None, jerry: Cell | None = None,
               bruno: Cell | None = None, bruno_state: str = "SLEEP", keys: tuple[Cell, ...] = (),
               tom_stun: int = 0, exit_open: bool = False, fs: float = 12,
               coords: bool = True) -> None:
    """Draw walls, floor, kennel H, exit E, keys K and the characters (T, J, B) on `ax`."""
    ax.set_xlim(0, maze.cols)
    ax.set_ylim(maze.rows, 0)
    ax.set_aspect("equal")
    for r in range(maze.rows):
        for c in range(maze.cols):
            ax.add_patch(Rectangle((c, r), 1, 1, fc=FLOOR if (r, c) in maze.floor else WALL,
                                   ec="white", lw=0.6))
    k = maze.kennel
    ax.add_patch(Rectangle((k[1], k[0]), 1, 1, fc=KENNEL_C, ec="white", lw=0.6))
    ax.text(*_center(k), "H", ha="center", va="center", fontsize=fs, color="white",
            fontweight="bold")
    e = maze.exit
    ax.add_patch(Rectangle((e[1], e[0]), 1, 1, fc=EXIT_OPEN if exit_open else EXIT_LOCKED,
                           ec="white", lw=0.6))
    ax.text(*_center(e), "E", ha="center", va="center", fontsize=fs, color="white",
            fontweight="bold")
    for key in keys:
        ax.add_patch(Circle(_center(key), 0.36, fc=KEY_C, ec="#8a6d00", lw=1.2, zorder=3))
        ax.text(*_center(key), "K", ha="center", va="center", fontsize=fs - 1, zorder=4,
                fontweight="bold")
    if bruno is not None:
        x, y = _center(bruno)
        ax.add_patch(Rectangle((x - 0.36, y - 0.36), 0.72, 0.72, fc=BRUNO_C, ec="white",
                               lw=1.2, zorder=5))
        ax.text(x, y, "B", ha="center", va="center", fontsize=fs, color="white", zorder=6,
                fontweight="bold")
        if bruno_state == "SLEEP":
            ax.text(x + 0.3, y - 0.32, "z", fontsize=fs, fontweight="bold", color="#222",
                    zorder=7)
    for who, cell, color in (("T", tom, TOM_C), ("J", jerry, JERRY_C)):
        if cell is None:
            continue
        ax.add_patch(Circle(_center(cell), 0.4, fc=color, ec="black", lw=1.5, zorder=8))
        ax.text(*_center(cell), who, ha="center", va="center", fontsize=fs, zorder=9,
                fontweight="bold")
    if tom is not None and tom_stun:
        ax.text(*_center(tom, (0, -0.62)), "★" * tom_stun, ha="center", va="center",
                fontsize=fs - 2, color="#d4a000", zorder=10)
    if coords:
        ax.set_xticks([c + 0.5 for c in range(maze.cols)], [str(c) for c in range(maze.cols)])
        ax.set_yticks([r + 0.5 for r in range(maze.rows)], [str(r) for r in range(maze.rows)])
        ax.xaxis.tick_top()
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
    else:
        ax.axis("off")


def path_line(ax: Axes, cells: list[Cell], color: str, style: str = "-", lw: float = 4,
              off: tuple[float, float] = (0, 0)) -> None:
    """Polyline through the centres of `cells`, with an arrow head at the end.
    Drawn under the characters (zorder 4) so Bruno and Jerry stay visible."""
    if len(cells) < 2:
        return
    pts = [_center(c, off) for c in cells]
    ax.plot([p[0] for p in pts[:-1]], [p[1] for p in pts[:-1]], style, color=color, lw=lw,
            alpha=0.9, zorder=4, solid_capstyle="round")
    ax.annotate("", xy=pts[-1], xytext=pts[-2], zorder=4,
                arrowprops={"arrowstyle": "-|>", "color": color, "lw": lw, "mutation_scale": 20})


# ------------------------------------------------------------------ figures


def maze_png(sc, path: Path) -> None:  # noqa: ANN001 (Scenario, avoids a circular import)
    """The scenario position with the A*, DLS and minimax overlays and a legend."""
    s = sc.state
    fig, ax = plt.subplots(figsize=(7.2, 7.9))
    draw_board(ax, s.maze, tom=s.tom, jerry=s.jerry, bruno=s.bruno.pos,
               bruno_state=s.bruno.state, keys=s.keys, exit_open=s.exit_open)
    path_line(ax, sc.hunt.path, TOM_C, "--", 4, (0, -0.2))
    path_line(ax, sc.evade.best_path, "#1f77b4", "-", 4, (0, 0.0))
    path_line(ax, sc.kennel_run.path, "#7b2cbf", ":", 4, (0, 0.2))
    for role in ("TOM", "JERRY"):
        start = s.tom if role == "TOM" else s.jerry
        move = sc.minimax[role].pv[0]
        nxt = move[2] if role == "TOM" else move[3]
        if nxt != start:
            ax.annotate("", xy=_center(nxt, (0, -0.42)), xytext=_center(start, (0, -0.42)),
                        zorder=12, arrowprops={"arrowstyle": "-|>", "color": "#c2185b",
                                               "lw": 3.5, "mutation_scale": 24})
    handles = [
        Line2D([], [], color=TOM_C, ls="--", lw=3, label="Tom HUNT: A* path to Jerry"),
        Line2D([], [], color="#1f77b4", lw=3, label="Jerry EVADE: DLS depth-5 best path"),
        Line2D([], [], color="#7b2cbf", ls=":", lw=3, label="Jerry RUN_FOR_BRUNO: A* to kennel"),
        Line2D([], [], color="#c2185b", lw=3, marker=">", label="minimax chosen move (both)"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=1,
              frameon=False, fontsize=10)
    ax.set_title(f"Scenario, turn {s.turn}: T Tom, J Jerry, B Bruno (asleep in kennel H), "
                 f"K last key, E exit (locked)", fontsize=10.5, pad=24)
    save(fig, path)


def _curve(ax: Axes, var: FuzzyVar, x_lo: float, x_hi: float, **kw) -> None:
    n = 400
    xs = [x_lo + (x_hi - x_lo) * i / n for i in range(n + 1)]
    for i, (name, mf) in enumerate(var.sets.items()):
        ax.plot(xs, [mf(x) for x in xs], color=SET_COLORS[i], lw=2, label=name, **kw)


def fuzzy_png(trace: dict, inputs: list[FuzzyVar], output: FuzzyVar, path: Path,
              title: str) -> None:
    """Membership curves of each input with the crisp value marked, plus the output panel
    with the clipped aggregate shaded and the centroid line."""
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 7.2))
    for ax, var in zip(axes.flat, inputs, strict=False):
        x = min(var.hi, max(var.lo, trace["inputs"][var.name]))
        _curve(ax, var, var.lo, var.hi)
        ax.axvline(x, color="black", ls="--", lw=1.5)
        shown = 0
        for i, (name, mf) in enumerate(var.sets.items()):
            mu = mf(x)
            if mu > 0:
                ax.plot([x], [mu], "o", color=SET_COLORS[i], ms=8, zorder=5)
                right = x > (var.lo + var.hi) / 2
                ax.annotate(f"{name} = {mu:.2f}", (x, mu),
                            xytext=(-10 if right else 10, 8 + 15 * shown),
                            textcoords="offset points", fontsize=10, color=SET_COLORS[i],
                            fontweight="bold", ha="right" if right else "left")
                shown += 1
        ax.set_title(f"input {var.name} = {trace['inputs'][var.name]:g}")
        ax.set_ylim(-0.05, 1.3)
        ax.set_xlabel(var.name)
        ax.set_ylabel("membership")
        ax.legend(loc="center right")
        ax.grid(alpha=0.3)
    ax = axes.flat[3]
    _curve(ax, output, output.lo, output.hi, ls="--", alpha=0.6)
    xs = [p[0] for p in trace["aggregated"]]
    mus = [p[1] for p in trace["aggregated"]]
    ax.fill_between(xs, mus, color="#f4a261", alpha=0.65, label="aggregate (clip, max)")
    ax.axvline(trace["centroid"], color="black", lw=2)
    ax.set_title(f"output {output.name}: centroid {trace['centroid']:.2f} → {trace['mode']}",
                 fontweight="bold")
    ax.set_ylim(-0.05, 1.3)
    ax.set_xlabel(output.name)
    ax.set_ylabel("membership")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    save(fig, path)


def _box(ax: Axes, x: float, y: float, w: float, h: float, lines: list[str], fc: str,
         ec: str = "black", lw: float = 1.2, fs: float = 9, bold: bool = False,
         color: str = "black") -> None:
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc=fc, ec=ec, lw=lw, zorder=3))
    ax.text(x, y, "\n".join(lines), ha="center", va="center", fontsize=fs, zorder=4,
            fontweight="bold" if bold else "normal", color=color, linespacing=1.25)


def _fmt(v: object) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return {"inf": "∞", "-inf": "−∞"}[v]
    return f"{v:g}".replace("-", "−")


def minimax_tree_png(trace: dict, path: Path, title: str) -> None:
    """Alpha-beta tree: plies 0-2 as boxes (move, value, alpha, beta), ply 3 as small boxes
    stacked under their parent. Pruned branches grey, principal variation green."""
    nodes = {n["id"]: n for n in trace["tree"]}
    kids: dict[int, list[int]] = {}
    for n in trace["tree"]:
        if n["parent"] is not None:
            kids.setdefault(n["parent"], []).append(n["id"])

    # principal variation: from the root, the first unpruned child with the node's value
    pv = {0}
    cur = 0
    while kids.get(cur):
        nxt = next((i for i in kids[cur] if not nodes[i]["pruned"]
                    and nodes[i]["value"] == nodes[cur]["value"]), None)
        if nxt is None:
            break
        pv.add(nxt)
        cur = nxt

    # x slots: ply-2 nodes in order (pruned stubs are narrow); parents centre on children
    x: dict[int, float] = {}
    cursor = 0.0
    for p1 in kids[0]:
        for p2 in kids.get(p1, []):
            w = 0.7 if nodes[p2]["pruned"] else 1.25
            x[p2] = cursor + w / 2
            cursor += w
        if kids.get(p1):
            x[p1] = (x[kids[p1][0]] + x[kids[p1][-1]]) / 2
        else:  # pruned ply-1 node (no children recorded)
            x[p1] = cursor + 0.35
            cursor += 0.7
    x[0] = (x[kids[0][0]] + x[kids[0][-1]]) / 2

    ys = {0: 0.0, 1: -1.7, 2: -3.4, 3: -4.55}
    n3 = max((len(kids.get(i, [])) for i in nodes if nodes[i]["ply"] == 2), default=1)
    fig, ax = plt.subplots(figsize=(max(9.5, cursor + 1.9), 4.2 + 0.32 * n3))
    root_player = trace["root_player"]

    def label(i: int) -> list[str]:
        n = nodes[i]
        if n["pruned"]:
            return [str(n["move"]), "pruned"]
        who = "Tom" if n["player"] != "TOM" else "Jerry"  # the player who just moved
        return [f"{who}: {n['move']}", f"v = {_fmt(n['value'])}",
                f"α {_fmt(n['alpha'])}  β {_fmt(n['beta'])}"]

    for i, n in nodes.items():
        p = n["parent"]
        if p is None or n["ply"] > 2:
            continue
        on_pv = i in pv
        ax.plot([x[p], x[i]], [ys[n["ply"] - 1] - 0.4, ys[n["ply"]] + 0.4],
                color=PV_C if on_pv else "#888", lw=3 if on_pv else 1.2, zorder=1)
    for i, n in nodes.items():
        ply = n["ply"]
        if ply == 0:
            _box(ax, x[0], ys[0], 3.2, 0.85, [f"ROOT: {root_player.title()} to move",
                 f"v = {_fmt(n['value'])}   (chosen {trace['chosen']})"], "#fff3cd", PV_C, 3,
                 fs=9.5, bold=True)
        elif ply <= 2:
            w = 0.62 if n["pruned"] else 1.15
            _box(ax, x[i], ys[ply], w, 0.8 if not n["pruned"] else 0.55, label(i),
                 PRUNED_C if n["pruned"] else "white", PV_C if i in pv else "black",
                 3 if i in pv else 1.2, fs=7.5 if n["pruned"] else 9)
    for p2 in (i for i, n in nodes.items() if n["ply"] == 2 and not n["pruned"]):
        for j, c in enumerate(kids.get(p2, [])):
            n = nodes[c]
            yy = ys[3] - 0.34 * j
            ax.plot([x[p2], x[p2]], [ys[2] - 0.4, yy + 0.15], color="#bbb", lw=0.8, zorder=1)
            txt = f"{n['move']}  pruned" if n["pruned"] else f"{n['move']}  {_fmt(n['value'])}"
            _box(ax, x[p2], yy, 1.15, 0.3, [txt], PRUNED_C if n["pruned"] else "white",
                 PV_C if c in pv else "#666", 2.5 if c in pv else 0.8, fs=8.5)
    xl = -1.9
    for ply, text in enumerate(["ply 0", "ply 1", "ply 2", "ply 3"]):
        mover = ("Tom MAX", "Jerry MIN")[(ply + (root_player != "TOM")) % 2]
        ax.text(xl, ys[ply] - (0.4 if ply == 3 else 0), f"{text}\n{mover}\nto move",
                ha="left", va="center", fontsize=9, color="#444")
    ax.set_xlim(xl - 0.1, cursor + 0.2)
    ax.set_ylim(ys[3] - 0.34 * n3 - 0.2, 0.75)
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.text((cursor - 1.9) / 2, ys[3] - 0.34 * n3 - 0.05,
            "Each box: move that led here, minimax value v, alpha, beta. Grey = pruned "
            "(alpha >= beta). Green = principal variation. Ply-3 values are backed up from "
            "the static evaluation one ply deeper (depth 4).", ha="center", va="top",
            fontsize=8.5, color="#333", wrap=True)
    save(fig, path)


def _mcts_tree(ax: Axes, trace: dict, title: str) -> None:
    kids = trace["root_children"]
    root = trace["tree"][0]
    ax.set_xlim(0, 4.2)
    ax.set_ylim(-3.3, 0.8)
    ax.axis("off")
    _box(ax, 2.1, 0.0, 2.8, 0.8, [f"root: visits {root['visits']}", f"wins {root['wins']:g}"],
         "#fff3cd", PV_C, 2.5, fs=10, bold=True)
    for i, k in enumerate(kids):
        cx, cy = 0.75 + i * 1.35, -2.0
        chosen = k["target"] == trace["chosen"]
        ax.plot([2.1, cx], [-0.4, cy + 0.9], color=PV_C if chosen else "#888",
                lw=3 if chosen else 1.2, zorder=1)
        ucb = k["ucb"] if isinstance(k["ucb"], str) else f"{k['ucb']:.2f}"
        _box(ax, cx, cy, 1.25, 1.8, [f"target\n({k['target'][0]},{k['target'][1]})",
             f"visits {k['visits']}", f"wins {k['wins']:g}", f"win rate\n{k['win_rate']:.2f}",
             f"UCB {ucb}"], "#e8f5e9" if chosen else "white", PV_C if chosen else "black",
             3 if chosen else 1.2, fs=9)
    ax.set_title(title, fontsize=11, fontweight="bold")


def mcts_png(sc, path: Path) -> None:  # noqa: ANN001
    """Two columns: Jerry visible (real position) and Jerry unseen for a while. Top: the
    two-level UCT tree. Bottom: the board with the sampled opponent cells (counts)."""
    s = sc.state
    fig, axes = plt.subplots(2, 2, figsize=(10, 8.6), gridspec_kw={"height_ratios": [1, 1.25]})
    hidden_age = sc.hidden_obs.turn - s.turn
    cases = [(sc.mcts_seen, "A: real position (Jerry visible)"),
             (sc.mcts_hidden, f"B: what if Jerry was unseen for {hidden_age} turns")]
    for col, (res, name) in enumerate(cases):
        _mcts_tree(axes[0][col], res.trace, f"{name}\nTom's MCTS, {res.iterations} iterations")
        ax = axes[1][col]
        draw_board(ax, s.maze, tom=s.tom, jerry=s.jerry if col == 0 else None,
                   bruno=s.bruno.pos, bruno_state=s.bruno.state, keys=s.keys, fs=10)
        for cell, n in res.samples.items():
            ax.add_patch(Circle(_center(cell), 0.22 + 0.2 * n / max(res.samples.values()),
                                fc="#e91e63", ec="white", lw=1.5, alpha=0.8, zorder=4))
            ax.text(*_center(cell, (0.62, 0)), str(n), ha="left", va="center", fontsize=9,
                    color="#c2185b", fontweight="bold", zorder=11,
                    bbox={"fc": "white", "ec": "none", "pad": 1})
        ax.set_xlabel("pink dots: sampled opponent cell, number = times sampled", fontsize=9)
    fig.tight_layout()
    save(fig, path)


def bruno_strip_png(maze: Maze, keys: tuple[Cell, ...], frames: list, path: Path) -> None:
    """All rounds of the Bruno scenario as a grid of small boards."""
    cols = 2
    rows = (len(frames) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(8.2, 2.35 * rows))
    for ax in axes.flat:
        ax.axis("off")
    for ax, f in zip(axes.flat, frames, strict=False):
        draw_board(ax, maze, tom=f.tom, jerry=f.jerry, bruno=f.bruno, bruno_state=f.bruno_state,
                   keys=keys, tom_stun=f.tom_stun, fs=11, coords=False)
        what = "; ".join(f.events) if f.events else "-"
        ax.set_title(f"Round {f.round}   Bruno {f.bruno_state}   Tom stun {f.tom_stun}",
                     fontsize=10.5, fontweight="bold", loc="left")
        ax.text(0, maze.rows + 0.25, what, fontsize=8.5, va="top", color="#333")
    fig.tight_layout()
    save(fig, path)
