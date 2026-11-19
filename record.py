"""Headless AI-vs-AI recording: one frame per turn (whole window, right panel included) -> mp4.

Frames are 1100x720 and written at 8 fps, one frame per turn, so the video runs at 8 turns per
second: 4x the game's default spectator speed of 2 turns/s. Seeds and windows come from
results/demo_seeds.json (scripts/find_demo_seeds.py).

Usage: python record.py [--only bruno_saves_jerry,full_game] [--out videos]
       python record.py --seed 5 --from 0 --to 40 --name custom   (HARD vs HARD)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import pygame  # noqa: E402

import config as C  # noqa: E402
import main  # noqa: E402

SEEDS_FILE = Path("results/demo_seeds.json")
FPS = 8
END_HOLD = 12  # frames shown with the end screen
# per video: file name, fps, overlays
VIDEOS = {
    "bruno_saves_jerry": ("a_bruno_saves_jerry.mp4", FPS, {"path": True}),
    "minimax_chase": ("b_minimax_close_chase.mp4", FPS, {"path": True}),
    "fuzzy_switch": ("c_fuzzy_mode_switch.mp4", 4, {}),  # slower: the fuzzy bars must be readable
    "full_game": ("d_full_game_hard_vs_hard.mp4", FPS, {}),
}


def frame(screen: pygame.Surface) -> np.ndarray:
    """Current screen as an (H, W, 3) uint8 array."""
    return np.ascontiguousarray(pygame.surfarray.array3d(screen).swapaxes(0, 1))


def record(
    seed: int,
    first: int,
    last: int,
    path: Path,
    fps: int,
    overlay: dict[str, bool],
    tom: str = "hard",
    jerry: str = "hard",
    size: int = C.DEFAULT_SIZE,
) -> int:
    """Play a seeded AI-vs-AI game; write a frame after each round whose turn is in
    [first, last]. Returns the number of frames written."""
    pygame.init()
    screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H))
    app = main.App(
        screen,
        main.parse_args(["--seed", str(seed), "--tom", tom, "--jerry", jerry, "--size", str(size)]),
    )
    app.start_game(main.WATCH)
    app.overlay.update(overlay)
    app.speed = main.SPEEDS.index(fps)  # top bar shows the video speed in turns per second
    s = app.session
    assert s is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with imageio.get_writer(
        str(path), fps=fps, codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=1
    ) as w:
        if first == 0:
            app.draw()
            w.append_data(frame(screen))
            n += 1
        while s.state.winner is None and s.state.turn <= last:
            before = s.state.turn
            s.ai_round()
            if before >= first:
                app.draw()
                w.append_data(frame(screen))
                n += 1
        if s.state.winner is not None:
            app.scene = "end"
            app.draw()
            for _ in range(END_HOLD):
                w.append_data(frame(screen))
                n += 1
    pygame.quit()
    return n


def main_() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="videos")
    p.add_argument("--only", default="")
    p.add_argument("--seed", type=int)
    p.add_argument("--from", dest="first", type=int, default=0)
    p.add_argument("--to", dest="last", type=int, default=C.TURN_LIMIT + 1)
    p.add_argument("--name", default="custom")
    args = p.parse_args()
    out = Path(args.out)
    if args.seed is not None:
        n = record(args.seed, args.first, args.last, out / f"{args.name}.mp4", FPS, {})
        print(f"{out / (args.name + '.mp4')}: {n} frames")
        return
    seeds = json.loads(SEEDS_FILE.read_text(encoding="utf-8"))
    setup = seeds["setup"]
    only = [k for k in args.only.split(",") if k]
    for key, (name, fps, overlay) in VIDEOS.items():
        if only and key not in only:
            continue
        v = seeds[key]
        n = record(
            v["seed"],
            v["from"],
            v["to"],
            out / name,
            fps,
            overlay,
            v["tom"].lower(),
            v["jerry"].lower(),
            setup["size"],
        )
        print(
            f"{out / name}: seed {v['seed']} turns {v['from']}-{v['to']}, {n} frames at {fps} fps"
        )


if __name__ == "__main__":
    main_()
