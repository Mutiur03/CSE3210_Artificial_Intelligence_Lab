"""Algorithm explainer videos: one clip per algorithm, each in real game situations.

Drives the same `demo.Demo` screen the live game uses (so every number comes from
search.py / minimax.py / mcts.py / fuzzy.py), animates it frame by frame and writes
videos/algorithms/<name>.mp4 plus videos/algorithms/all_algorithms.mp4.

    python scripts/algo_videos.py [--only astar,minimax] [--seed 7]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import pygame  # noqa: E402

import config as C  # noqa: E402
import render3d  # noqa: E402
import ui  # noqa: E402
from demo import Demo  # noqa: E402
from maze import Maze, generate_maze  # noqa: E402
from search import Cell  # noqa: E402

FPS = 24
OUT = Path("videos/algorithms")


class Sink:
    """Frame writer for one clip, mirrored into the master video."""

    def __init__(self, screen: pygame.Surface, name: str, master: object) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        self.screen, self.master = screen, master
        self.w = imageio.get_writer(str(OUT / f"{name}.mp4"), fps=FPS, codec="libx264", quality=8,
                                    pixelformat="yuv420p", macro_block_size=1)

    def frame(self, n: int = 1) -> None:
        arr = np.ascontiguousarray(pygame.surfarray.array3d(self.screen).swapaxes(0, 1))
        for _ in range(n):
            self.w.append_data(arr)
            self.master.append_data(arr)  # type: ignore[attr-defined]

    def close(self) -> None:
        self.w.close()


def title_card(sink: Sink, fonts: ui.Fonts, title: str, lines: list[str]) -> None:
    s = sink.screen
    s.fill(C.COLOR_BG)
    ui.text(s, fonts.title, title, (C.WINDOW_W // 2, 250), C.COLOR_ACCENT, center=True)
    for i, line in enumerate(lines):
        ui.text(s, fonts.big if i == 0 else fonts.normal, line,
                (C.WINDOW_W // 2, 340 + i * 44), C.COLOR_TEXT, center=True)
    sink.frame(FPS * 3)


def cells_at(maze: Maze, origin: Cell, dist: int) -> Cell:
    """Floor cell whose path distance from `origin` is `dist` (first in row order)."""
    dm = maze.dist_map(origin)
    return next(c for c in sorted(maze.floor) if dm[c] == dist)


def play_search(sink: Sink, demo: Demo, caption: str, seconds: float = 7.0) -> None:
    """Animate the expansion order of the current search, then hold the result."""
    demo.caption = caption
    demo.progress = 0.0
    total = max(1, len(demo.order))
    step = max(0.4, total / (FPS * seconds))
    while demo.shown() < total:
        demo.draw(sink.screen)
        sink.frame()
        demo.progress += step
    demo.progress = total + 1
    demo.draw(sink.screen)
    sink.frame(FPS * 2)


def setup(demo: Demo, algo: int, start: Cell, goal: Cell, tom_first: bool = False,
          **kw: int) -> None:
    demo.algo, demo.compare, demo.start, demo.goal = algo, False, start, goal
    demo.tom_first = tom_first
    for k, v in kw.items():
        setattr(demo, k, v)
    demo.compute()


# ------------------------------------------------------------------ clips

def clip_astar(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "A*", ["Tom HUNT: shortest path to Jerry",
               "f = g + h,  g = steps so far,  h = Manhattan distance to the goal",
               "Always expands the open cell with the lowest f"])
    setup(demo, 1, m.tom_start, m.jerry_start, tom_first=True)
    play_search(sink, demo, "Situation 1: Tom (S) hunts Jerry (G). Blue = expanded, "
                "yellow = open list, green = final path")
    near = cells_at(m, m.jerry_start, 7)
    setup(demo, 1, near, m.jerry_start, tom_first=True)
    play_search(sink, demo, "Situation 2: Jerry is close. Few expansions: h points straight at him")


def clip_greedy(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Greedy best-first", ["EASY Tom: always expand the cell with the lowest h",
               "Fast, but ignores g: the path can be longer than A*'s"])
    setup(demo, 2, m.tom_start, m.jerry_start, tom_first=True)
    play_search(sink, demo, "EASY Tom chases Jerry: expands whatever looks closest (h only)")
    demo.compare, demo.caption = True, "Same maze, same start and goal: A* (left) vs greedy (right)"
    demo.compute()
    total = max(len(demo.res.explored_order), len(demo.res2.explored_order))  # type: ignore[union-attr]
    demo.progress = 0.0
    while demo.progress < total:
        demo.draw(sink.screen)
        sink.frame()
        demo.progress += max(0.5, total / (FPS * 8))
    demo.draw(sink.screen)
    sink.frame(FPS * 3)
    demo.compare = False


def clip_dfs(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "DFS", ["Tom SWEEP: search the maze when Jerry is lost",
               "Go as deep as possible, backtrack at dead ends",
               "Also builds the maze (recursive backtracker)"])
    far = max(m.floor, key=lambda c: m.dist_map(m.tom_start)[c])
    setup(demo, 3, m.tom_start, far, tom_first=True)
    play_search(sink, demo, "Tom has lost Jerry (age > 12): DFS sweeps corridor after corridor", 9)


def clip_dls(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Depth-limited search", ["Jerry EVADE: look exactly 5 steps ahead",
               "A path is SAFE if Jerry reaches each cell before Tom can",
               "Cutoff cells (red) are where the depth limit stopped the search"])
    tom = m.tom_start
    for dist, text in ((6, "Tom 6 steps away: many safe 5-step escape paths"),
                       (3, "Tom only 3 steps away: few safe paths, Jerry picks the best score")):
        setup(demo, 4, cells_at(m, tom, dist), tom, dls_limit=C.DLS_DEPTH)
        play_search(sink, demo, f"Situation: {text}. Magenta = chosen escape path", 6)


def clip_bidir(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Bidirectional search", ["Tom AMBUSH: meet Jerry halfway to his next key",
               "Two BFS waves, one from Tom, one from the key",
               "Stop when they touch: the meeting cell"])
    key = m.keys[0]
    setup(demo, 5, m.tom_start, key, tom_first=True)
    play_search(sink, demo, "Tom (S) ambushes Jerry's likely next key (G): blue wave from Tom, "
                "orange from the key", 8)


def clip_minimax(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Minimax + alpha-beta", ["HARD close range: Tom looks 4 plies ahead",
               "Tom maximises, Jerry minimises; branches that cannot matter are pruned",
               "Leaf value = distance, escape routes, Bruno, stun, dead ends"])
    j = m.jerry_start
    for dist in (3, 4):
        setup(demo, 6, j, cells_at(m, j, dist))
        tree = [n for n in (demo.mm.trace or {}).get("tree", []) if n["ply"] <= 2][:40]
        demo.caption = f"Tom is {dist} steps from Jerry: the tree grows node by node"
        for k in range(1, len(tree) + 1):
            demo.reveal = k
            demo.draw(sink.screen)
            sink.frame(4)
        demo.reveal = None
        demo.caption = f"Chosen: {demo.mm.action}  (green branch), grey = pruned by alpha-beta"
        demo.draw(sink.screen)
        sink.frame(FPS * 3)


def clip_mcts(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Monte Carlo Tree Search", ["NIGHTMARE Tom: pick the best ambush target",
               "Guess where Jerry is (magenta dots), simulate 20 turns, count catches",
               "Visits grow on the targets that work (UCB1)"])
    close = cells_at(m, m.tom_start, 9)
    for age, label in ((3, "Jerry seen 3 turns ago: few possible cells"),
                       (12, "Jerry unseen for 12 turns: dots spread out, Tom is less sure")):
        demo.algo, demo.compare, demo.start, demo.goal, demo.mcts_age = 7, False, close, \
            m.tom_start, age
        for n in (5, 15, 40, 100, 200, C.MCTS_ITERATIONS):
            demo.mcts_iters = n
            demo.compute()
            demo.caption = f"{label}. After {n} of {C.MCTS_ITERATIONS} iterations"
            demo.draw(sink.screen)
            sink.frame(int(FPS * 1.4))
        sink.frame(FPS)
    demo.mcts_iters = C.MCTS_ITERATIONS


def clip_fuzzy(sink: Sink, demo: Demo, m: Maze) -> None:
    title_card(sink, demo.fonts,
               "Fuzzy logic (Mamdani)", ["Tom and Jerry pick a mode every turn",
               "Inputs become membership degrees, rules fire, outputs are clipped and merged",
               "The centroid of the shape gives the mode"])
    demo.algo, demo.compare = 8, False
    sweeps: list[tuple[str, str, str, float, float, int]] = [
        ("TOM", "dist", "Tom: Jerry gets farther away (age fresh)", 1.0, 28.0, 90),
        ("TOM", "age", "Tom: Jerry out of sight for longer", 0.0, 30.0, 90),
        ("TOM", "bruno", "Tom: Bruno closes in", 0.0, 1.0, 70),
        ("JERRY", "danger", "Jerry: Tom approaches (2 keys left)", 28.0, 1.0, 90),
        ("JERRY", "keys_left", "Jerry: collecting the last key", 3.0, 0.0, 70),
    ]
    for role, var, text, a, b, frames in sweeps:
        demo.fz_role = role
        names = list(demo.controllers[role].inputs)
        demo.fz_sel = names.index(var)
        base = {"TOM": {"dist": 6.0, "age": 0.0, "bruno": 0.0},
                "JERRY": {"danger": 12.0, "keys_left": 2.0, "bruno_ready": 0.0}}[role]
        demo.fz_inputs[role] = dict(base)
        for i in range(frames):
            demo.fz_inputs[role][var] = a + (b - a) * i / (frames - 1)
            demo.caption = f"{text}: {var} = {demo.fz_inputs[role][var]:.1f}"
            demo.draw(sink.screen)
            sink.frame()
        sink.frame(FPS)


CLIPS: dict[str, Callable[[Sink, Demo, Maze], None]] = {
    "astar": clip_astar, "greedy": clip_greedy, "dfs": clip_dfs, "dls": clip_dls,
    "bidirectional": clip_bidir, "minimax": clip_minimax, "mcts": clip_mcts,
    "fuzzy": clip_fuzzy,
}
ORDER = list(CLIPS)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", default="")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    only = [k for k in args.only.split(",") if k] or ORDER
    render3d.TWEEN_S = 0
    pygame.init()
    screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H))
    maze = generate_maze(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    master = imageio.get_writer(str(OUT / "all_algorithms.mp4"), fps=FPS, codec="libx264",
                                quality=8, pixelformat="yuv420p", macro_block_size=1)
    fonts = ui.Fonts()
    for name in ORDER:
        if name not in only:
            continue
        demo = Demo(maze, fonts, args.seed)
        sink = Sink(screen, name, master)
        CLIPS[name](sink, demo, maze)
        sink.close()
        print(f"{OUT / (name + '.mp4')} done", flush=True)
    master.close()
    pygame.quit()


if __name__ == "__main__":
    main()
