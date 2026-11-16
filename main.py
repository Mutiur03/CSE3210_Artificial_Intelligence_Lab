"""Cheese Heist entry point: menu, game loop, input.

Run: python main.py [--seed N] [--size 21] [--no-bruno]
Headless screenshot: python main.py --seed 190 --auto 46 --screenshot docs/screens/phase1.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

if "--screenshot" in sys.argv:  # headless capture must pick drivers before pygame starts
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import config as C  # noqa: E402
import ui  # noqa: E402
from agents import Decision, RandomAgent  # noqa: E402
from game import (  # noqa: E402
    JERRY,
    TOM,
    GameState,
    Observation,
    legal_actions,
    make_observation,
    new_game,
    run_round,
)
from maze import generate_maze  # noqa: E402

MOVE_KEYS = {
    pygame.K_UP: "UP", pygame.K_w: "UP", pygame.K_DOWN: "DOWN", pygame.K_s: "DOWN",
    pygame.K_LEFT: "LEFT", pygame.K_a: "LEFT", pygame.K_RIGHT: "RIGHT", pygame.K_d: "RIGHT",
    pygame.K_SPACE: "WAIT",
}
END_BUTTONS = ["Replay same seed (R)", "New game (N)", "Menu (M)"]


@dataclass
class Session:
    """One game: human Jerry vs AI Tom (RandomAgent in phase 1)."""

    seed: int
    size: int
    bruno: bool
    state: GameState = field(init=False)
    tom: RandomAgent = field(init=False)
    decision: Decision | None = None
    log: list[str] = field(default_factory=list)
    tom_nodes: int = 0

    def __post_init__(self) -> None:
        self.state = new_game(generate_maze(self.seed, self.size), self.bruno)
        self.tom = RandomAgent(self.seed)

    def tom_policy(self, obs: Observation) -> str:
        self.decision = self.tom.act(obs)
        self.tom_nodes += self.decision.nodes
        return self.decision.action

    def human_move(self, action: str) -> bool:
        """Play one round with the human's action. False if the move is blocked."""
        if action not in legal_actions(self.state, JERRY):
            return False
        turn = self.state.turn
        events = run_round(self.state, lambda _obs: action, self.tom_policy)
        self.log += [f"T{turn}: {e.text}" for e in events if JERRY in e.audience]
        return True

    def panel(self) -> ui.PanelInfo:
        obs = make_observation(self.state, JERRY)
        d = self.decision
        if obs.opp_pos is not None:
            belief = f"Tom visible at {obs.opp_pos}"
        elif obs.opp_last_seen is not None:
            pos, seen = obs.opp_last_seen
            belief = f"Tom last seen at {pos}, age {self.state.turn - seen}"
        else:
            belief = "Tom not seen yet"
        b = self.state.bruno
        if b is None:
            bruno = ["Disabled"]
        elif obs.bruno is None:
            bruno = ["Not in sight", f"Activations used: {b.activations}/2"]
        else:
            bruno = [f"State: {b.state}  at {b.pos}",
                     f"Guard {b.guard_timer}  Tired {b.tired_timer}  Bite cd {b.bite_cooldown}",
                     f"Activations used: {b.activations}/2"]
        return ui.PanelInfo(
            role=TOM, mode=d.mode if d else "-", algorithm=d.algorithm if d else "-",
            nodes=d.nodes if d else 0, ms=d.ms if d else 0.0, belief=belief, bruno=bruno,
            events=self.log,
        )

    def stats(self) -> list[str]:
        s, b = self.state, self.state.bruno
        return [
            f"Turns played: {min(s.turn, C.TURN_LIMIT)}",
            f"Keys collected: {s.keys_taken}/{C.NUM_KEYS}",
            f"Bruno activations: {b.activations if b else 0}   Bites: {s.bites}",
            f"Nodes searched  Tom: {self.tom_nodes}   Jerry: human",
            f"Seed {self.seed}, size {self.size}",
        ]


class App:
    """Scene machine: 'menu' -> 'game' -> 'end'."""

    def __init__(self, screen: pygame.Surface, args: argparse.Namespace) -> None:
        self.screen = screen
        self.fonts = ui.Fonts()
        self.size, self.seed, self.bruno = args.size, args.seed, not args.no_bruno
        self.scene = "menu"
        self.selected = 0
        self.seed_buf: str | None = None
        self.session: Session | None = None
        self.rects: list[pygame.Rect] = []
        self.running = True

    # ---------------------------------------------------------- menu
    def menu_items(self) -> list[str]:
        seed = f"{self.seed_buf}_" if self.seed_buf is not None else str(self.seed)
        return ["Play as Jerry", f"Map size: {self.size}", f"Seed: {seed}",
                f"Bruno: {'On' if self.bruno else 'Off'}", "Quit"]

    def menu_activate(self, delta: int = 1) -> None:
        item = self.menu_items()[self.selected]
        if item.startswith("Play"):
            self.start_game()
        elif item.startswith("Map"):
            i = C.MAP_SIZES.index(self.size)
            self.size = C.MAP_SIZES[(i + delta) % len(C.MAP_SIZES)]
        elif item.startswith("Seed"):
            self.seed_buf = ""
        elif item.startswith("Bruno"):
            self.bruno = not self.bruno
        elif item == "Quit":
            self.running = False

    def menu_key(self, key: int, uni: str) -> None:
        if self.seed_buf is not None:  # typing a seed
            if uni.isdigit() and len(self.seed_buf) < 9:
                self.seed_buf += uni
            elif key == pygame.K_BACKSPACE:
                self.seed_buf = self.seed_buf[:-1]
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                if key != pygame.K_ESCAPE and self.seed_buf:
                    self.seed = int(self.seed_buf)
                self.seed_buf = None
            return
        n = len(self.menu_items())
        if key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.menu_activate()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            label = self.menu_items()[self.selected]
            if label.startswith(("Map", "Bruno")):
                self.menu_activate(-1 if key in (pygame.K_LEFT, pygame.K_a) else 1)
        elif key == pygame.K_r:
            self.seed = random_seed()
        elif key == pygame.K_ESCAPE:
            self.running = False

    # ---------------------------------------------------------- game
    def start_game(self) -> None:
        self.session = Session(self.seed, self.size, self.bruno)
        self.scene = "game"

    def game_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.scene = "menu"
        elif key in MOVE_KEYS and self.session is not None:
            self.session.human_move(MOVE_KEYS[key])
            if self.session.state.winner is not None:
                self.scene = "end"

    def end_choice(self, idx: int) -> None:
        if idx == 0:
            self.start_game()
        elif idx == 1:
            self.seed = random_seed()
            self.start_game()
        else:
            self.scene = "menu"

    # ---------------------------------------------------------- loop
    def handle(self, ev: pygame.event.Event) -> None:
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN:
            if self.scene == "menu":
                self.menu_key(ev.key, ev.unicode)
            elif self.scene == "game":
                self.game_key(ev.key)
            elif self.scene == "end":
                keys = {pygame.K_r: 0, pygame.K_n: 1, pygame.K_m: 2, pygame.K_ESCAPE: 2}
                if ev.key in keys:
                    self.end_choice(keys[ev.key])
        elif ev.type == pygame.MOUSEMOTION and self.scene == "menu" and self.seed_buf is None:
            for i, r in enumerate(self.rects):
                if r.collidepoint(ev.pos):
                    self.selected = i
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            hit = next((i for i, r in enumerate(self.rects) if r.collidepoint(ev.pos)), None)
            if hit is not None and self.scene == "menu" and self.seed_buf is None:
                self.selected = hit
                self.menu_activate()
            elif hit is not None and self.scene == "end":
                self.end_choice(hit)

    def draw(self) -> None:
        if self.scene == "menu" or self.session is None:
            hint = "Arrows/mouse select, Enter choose, Left/Right change, R random seed"
            if self.seed_buf is not None:
                hint = "Type seed digits, Enter to confirm, Esc to cancel"
            self.rects = ui.draw_menu(self.screen, self.fonts, self.menu_items(), self.selected,
                                      hint)
            return
        s = self.session
        self.screen.fill(C.COLOR_BG)
        ui.draw_board(self.screen, self.fonts, s.state, make_observation(s.state, JERRY))
        ui.draw_top_bar(self.screen, self.fonts, s.state, JERRY, "Tom: RANDOM")
        ui.draw_panel(self.screen, self.fonts, s.panel())
        self.rects = []
        if self.scene == "end":
            self.rects = ui.draw_end(self.screen, self.fonts, s.state.winner or "", s.state.reason,
                                     s.stats(), END_BUTTONS)

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self.running:
            for ev in pygame.event.get():
                self.handle(ev)
            self.draw()
            pygame.display.flip()
            clock.tick(C.FPS)


def random_seed() -> int:
    """New seed for the menu's R key / New game. The game itself stays seeded."""
    return time.time_ns() % 1_000_000


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cheese Heist")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--size", type=int, default=C.DEFAULT_SIZE, choices=C.MAP_SIZES)
    p.add_argument("--no-bruno", action="store_true")
    p.add_argument("--screenshot", help="start a game, play --auto rounds, save PNG, exit")
    p.add_argument("--auto", type=int, default=0, help="rounds a seeded random Jerry plays first")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    pygame.init()
    screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H))
    pygame.display.set_caption(C.TITLE)
    app = App(screen, args)
    if args.screenshot:
        app.start_game()
        jerry = RandomAgent(args.seed + 1)
        for _ in range(args.auto):
            if app.session is None or app.session.state.winner is not None:
                break
            app.session.human_move(jerry.act(make_observation(app.session.state, JERRY)).action)
        if app.session is not None and app.session.state.winner is not None:
            app.scene = "end"
        app.draw()
        os.makedirs(os.path.dirname(args.screenshot) or ".", exist_ok=True)
        pygame.image.save(screen, args.screenshot)
        print(f"saved {args.screenshot}")
    else:
        app.run()
    pygame.quit()


if __name__ == "__main__":
    main()
