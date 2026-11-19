"""Save the documentation screenshots to docs/screens/ (headless).

Usage: python scripts/screens.py [--seed 7]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

import main  # noqa: E402
from agents import JerryAgent  # noqa: E402
from game import JERRY, make_observation  # noqa: E402

OUT = Path("docs/screens")


def save(app: main.App, name: str) -> None:
    app.draw()
    pygame.image.save(app.screen, str(OUT / name))
    print("saved", OUT / name)


def play_until_contact(app: main.App, max_rounds: int = 60) -> None:
    """Human-Jerry game driven by a NORMAL Jerry agent until Tom is in sight (turn >= 8)."""
    s = app.session
    assert s is not None
    bot = JerryAgent("NORMAL", 99)
    for _ in range(max_rounds):
        obs = make_observation(s.state, JERRY)
        if s.state.winner is not None or (obs.opp_pos is not None and s.state.turn >= 8):
            return
        s.human_move(bot.act(obs).action)


def main_() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.init()
    screen = pygame.display.set_mode((1100, 720))
    app = main.App(screen, main.parse_args(["--seed", str(args.seed), "--tom", "hard"]))
    save(app, "menu.png")
    app.run_action("How to Play")
    save(app, "help.png")
    app.help = False

    app.start_game(main.PLAY_JERRY)
    play_until_contact(app)
    save(app, "fog_view.png")
    app.overlay.update(path=True, explored=True)
    save(app, "game_panel.png")
    app.cycle_fuzzy()
    save(app, "fuzzy_panel.png")
    app.fuzzy_role = None
    app.overlay.update(path=False, explored=False)

    app.start_game(main.PLAY_TOM)
    for _ in range(12):
        app.session.human_move("WAIT")
    save(app, "play_as_tom.png")

    app.levels["JERRY"] = "HARD"
    app.start_game(main.WATCH)
    app.overlay.update(path=True, explored=True)
    for _ in range(30):
        if app.session.state.winner is None:
            app.session.ai_round()
    save(app, "spectator.png")
    while app.session.state.winner is None:
        app.session.ai_round()
    app.scene = "end"
    save(app, "end_screen.png")

    app.scene = "menu"
    app.open_demo()
    demo = app.demo
    names = {1: "astar", 2: "greedy", 3: "dfs", 4: "dls", 5: "bidirectional", 6: "minimax",
             7: "mcts", 8: "fuzzy"}
    for k, name in names.items():
        demo.key(getattr(pygame, f"K_{k}"))
        if k == 6:  # a close tactical position: Tom 4 steps from Jerry
            maze = demo.maze
            demo.goal = next(c for c, d in sorted(maze.dist_map(demo.start).items()) if d == 4)
            demo.compute()
        if k == 7:  # Tom 8 steps away: Jerry unseen, so MCTS samples where she may be
            maze = demo.maze
            demo.goal = next(c for c, d in sorted(maze.dist_map(demo.start).items()) if d == 8)
            demo.compute()
        if k == 8:  # compare view below uses the long Jerry-start -> Tom-start query
            demo.goal = demo.maze.tom_start
        if k in (1, 2, 3, 5):
            demo.progress = len(demo.order) * 0.55  # mid-animation: frontier visible
        else:
            demo.progress = 10_000.0
        save(app, f"demo_{k}_{name}.png")
    demo.key(pygame.K_c)
    demo.progress = 10_000.0
    save(app, "demo_compare.png")
    pygame.quit()


if __name__ == "__main__":
    main_()
