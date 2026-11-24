"""Cheese Heist entry point: menu, game loop, input.

Run: python main.py [--seed N] [--size 21] [--no-bruno] [--tom minimax|mcts] [--trace]
(Jerry's AI always uses the other algorithm.)
Headless screenshot: python main.py --seed 190 --auto 46 --screenshot docs/screens/x.png
(all documentation screenshots: python scripts/screens.py)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

if "--screenshot" in sys.argv:  # headless capture must pick drivers before pygame starts
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")  # smooth upscale to the window / screen

import pygame  # noqa: E402

import config as C  # noqa: E402
import ui  # noqa: E402
from agents import ALGORITHMS, LABEL, AIAgent, Decision, RandomAgent, make_agent, opposite  # noqa: E402
from demo import Demo  # noqa: E402
from game import (  # noqa: E402
    JERRY,
    TOM,
    TRAP,
    WHISTLE,
    Event,
    GameState,
    Observation,
    apply_action,
    end_of_round,
    gadget_ready,
    legal_actions,
    make_observation,
    new_game,
    other,
    run_round,
    use_gadget,
)
from maze import generate_maze  # noqa: E402

PLAY_JERRY, PLAY_TOM, WATCH = "PLAY_JERRY", "PLAY_TOM", "WATCH"
MOVE_KEYS = {
    pygame.K_UP: "UP", pygame.K_w: "UP", pygame.K_DOWN: "DOWN", pygame.K_s: "DOWN",
    pygame.K_LEFT: "LEFT", pygame.K_a: "LEFT", pygame.K_RIGHT: "RIGHT", pygame.K_d: "RIGHT",
    pygame.K_SPACE: "WAIT",
}
SPEEDS = (1, 2, 4, 8, 16)
END_BUTTONS = ["Replay same seed (R)", "New game (N)", "Menu (M)"]
TRACE_DIR = Path("results/traces")


@dataclass
class Session:
    """One game in one mode. Holds the AI agents and their latest decisions."""

    seed: int
    size: int
    bruno: bool
    mode: str
    tom_algo: str
    trace: bool = False
    state: GameState = field(init=False)
    agents: dict[str, AIAgent] = field(init=False)
    decisions: dict[str, Decision] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    nodes: dict[str, int] = field(default_factory=lambda: {TOM: 0, JERRY: 0})
    saved: int = 0

    def __post_init__(self) -> None:
        self.state = new_game(generate_maze(self.seed, self.size), self.bruno)
        self.agents = {r: make_agent(r, self.algos[r], self.seed * 2 + (r == TOM), self.trace)
                       for r in (TOM, JERRY) if r != self.human}
        if self.mode == PLAY_TOM:
            self.jerry_then_wait()

    @property
    def algos(self) -> dict[str, str]:
        """Tom's algorithm and the other one for Jerry: never the same in one game."""
        return {TOM: self.tom_algo, JERRY: opposite(self.tom_algo)}

    @property
    def human(self) -> str | None:
        return {PLAY_JERRY: JERRY, PLAY_TOM: TOM}.get(self.mode)

    def set_trace(self, on: bool) -> None:
        self.trace = on
        for agent in self.agents.values():
            agent.trace = on

    def policy(self, role: str) -> Callable[[Observation], str]:
        def act(obs: Observation) -> str:
            d = self.agents[role].act(obs)
            self.decisions[role] = d
            self.nodes[role] += d.nodes
            if self.trace and d.trace is not None:
                TRACE_DIR.mkdir(parents=True, exist_ok=True)
                path = TRACE_DIR / f"{self.seed}_{obs.turn}_{role}.json"
                path.write_text(json.dumps(d.trace, indent=1), encoding="utf-8")
                self.saved += 1
            return d.action
        return act

    def record(self, events: list[Event]) -> None:
        viewer = self.human
        self.log += [f"T{e.turn}: {e.text}" for e in events if viewer is None or viewer in
                     e.audience]

    def human_move(self, action: str) -> bool:
        """Play the human's action. False if the move is blocked by a wall."""
        role = self.human
        if role is None or action not in legal_actions(self.state, role):
            return False
        if role == JERRY:
            self.record(run_round(self.state, lambda _obs: action, self.policy(TOM)))
        else:
            self.record(apply_action(self.state, TOM, action))
            self.record(end_of_round(self.state))
            self.jerry_then_wait()
        return True

    def human_gadget(self, kind: str) -> bool:
        """Human Jerry's Q (trap) or E (whistle): spends her turn. False if not ready."""
        if self.human != JERRY or not gadget_ready(self.state, kind):
            return False
        self.record(use_gadget(self.state, kind))
        self.record(run_round(self.state, lambda _obs: "WAIT", self.policy(TOM)))
        return True

    def jerry_then_wait(self) -> None:
        """Human-Tom mode: the AI Jerry moves; while Tom is stunned his turns pass."""
        while self.state.winner is None:
            self.record(apply_action(self.state, JERRY, self.policy(JERRY)(
                make_observation(self.state, JERRY))))
            if self.state.winner is not None or self.state.tom_stun == 0:
                return
            self.record(apply_action(self.state, TOM, "WAIT"))
            self.record(end_of_round(self.state))

    def ai_round(self) -> None:
        """Spectator: one full round, both sides AI."""
        self.record(run_round(self.state, self.policy(JERRY), self.policy(TOM)))

    def ai_view(self, role: str) -> ui.AIView:
        d, agent = self.decisions.get(role), self.agents[role]
        opp = other(role).title()
        if agent.last_seen is None:
            belief = f"{opp} never seen"
        else:
            cell, seen = agent.last_seen
            age = self.state.turn - seen
            belief = f"{opp} last known at {cell}, turn {seen} (age {age})"
        if role == JERRY:
            belief += f";  Bruno {agent.bruno_state.lower()} {agent.activations}/2"
        if d is not None and d.fuzzy is not None and d.fuzzy_inputs is not None:
            ins = " ".join(f"{k}={v:g}" for k, v in d.fuzzy_inputs.items())
            belief += f";  fuzzy {ins} -> centroid {d.fuzzy.centroid:.0f} = {d.mode}"
        if role == TOM and agent.icpt is not None:
            i = agent.icpt
            belief += (f";  intercept: Jerry heads for {i.goal}, Tom meets her at {i.cell} "
                       f"(she needs {i.k})")
        if d is not None and d.corner:
            room = " ".join(f"{a[0]}{n}" for a, n in d.corner.items())
            belief += f";  corner check, room per move: {room}"
        if d is None:
            return ui.AIView(role, LABEL[agent.algo], "-", "waiting", 0, 0.0, belief)
        return ui.AIView(role, LABEL[agent.algo], d.mode, d.algorithm, d.nodes, d.ms, belief)

    def bruno_lines(self) -> list[str]:
        b = self.state.bruno
        if b is None:
            return ["Disabled"]
        lines = [f"{b.state} at {b.pos}   activations {b.activations}/2",
                 f"guard {b.guard_timer}   tired {b.tired_timer}   bite cooldown {b.bite_cooldown}"]
        if self.human == JERRY:
            if self.state.whistle_cd > 0:
                whistle = f"cooldown {self.state.whistle_cd}"
            else:
                whistle = "ready" if gadget_ready(self.state, WHISTLE) else "Bruno out of reach"
            lines.append(f"Q trap: {self.state.traps_left} left   E whistle: {whistle}")
        return lines

    def stats(self) -> list[str]:
        s, b = self.state, self.state.bruno
        nodes = [f"{r.title()} {self.nodes[r]}" if r in self.agents else f"{r.title()} human"
                 for r in (TOM, JERRY)]
        return [
            f"Turns played: {min(s.turn, C.TURN_LIMIT)}",
            f"Keys collected: {s.keys_taken}/{C.NUM_KEYS}",
            f"Bruno activations: {b.activations if b else 0}   Bites: {s.bites}",
            "Nodes searched:  " + "   ".join(nodes),
            matchup(self.algos, self.human),
            f"Seed {self.seed}, size {self.size}",
        ]


class App:
    """Scene machine: 'menu' -> 'game' -> 'end'; 'demo' and the help overlay on top."""

    ACTIONS = ["Play as Jerry", "Play as Tom", "Watch AI vs AI", "Algorithm Demo",
               "How to Play", "Quit"]

    def __init__(self, screen: pygame.Surface, args: argparse.Namespace) -> None:
        self.screen = screen
        self.fullscreen = False
        self.fonts = ui.Fonts()
        self.size, self.seed, self.bruno = args.size, args.seed, not args.no_bruno
        self.tom_algo = args.tom.upper()
        self.trace = args.trace
        self.scene = "menu"
        self.back_scene = "menu"
        self.help = False
        self.selected = 0
        self.seed_buf: str | None = None
        self.session: Session | None = None
        self.demo: Demo | None = None
        self.rects: list[pygame.Rect] = []
        self.overlay = {"path": False, "explored": False}
        self.paused = False
        self.notice = ""  # one-line feedback for the last human key (blocked move)
        self.speed = 2
        self.last_step = 0.0
        self.running = True

    def options(self) -> list[str]:
        seed = f"{self.seed_buf}_" if self.seed_buf is not None else str(self.seed)
        return [f"Tom AI: {LABEL[self.tom_algo]}",
                f"Jerry AI: {LABEL[opposite(self.tom_algo)]}",
                f"Map size: {self.size}", f"Seed: {seed}",
                f"Bruno: {'On' if self.bruno else 'Off'}"]

    def menu_activate(self, delta: int = 0) -> None:
        n = len(self.ACTIONS)
        if self.selected < n:
            if delta == 0:
                self.run_action(self.ACTIONS[self.selected])
            return
        opt = self.selected - n
        if opt in (0, 1):  # two algorithms: changing either side swaps both
            self.tom_algo = opposite(self.tom_algo)
        elif opt == 2:
            i = C.MAP_SIZES.index(self.size)
            self.size = C.MAP_SIZES[(i + (delta or 1)) % len(C.MAP_SIZES)]
        elif opt == 3:
            if delta == 0:
                self.seed_buf = ""
            else:
                self.seed = max(0, self.seed + delta)
        else:
            self.bruno = not self.bruno

    def run_action(self, action: str) -> None:
        if action == "Play as Jerry":
            self.start_game(PLAY_JERRY)
        elif action == "Play as Tom":
            self.start_game(PLAY_TOM)
        elif action == "Watch AI vs AI":
            self.start_game(WATCH)
        elif action == "Algorithm Demo":
            self.open_demo()
        elif action == "How to Play":
            self.help = True
        else:
            self.running = False

    def menu_key(self, key: int, uni: str) -> None:
        if self.seed_buf is not None:
            if uni.isdigit() and len(self.seed_buf) < 9:
                self.seed_buf += uni
            elif key == pygame.K_BACKSPACE:
                self.seed_buf = self.seed_buf[:-1]
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                if key != pygame.K_ESCAPE and self.seed_buf:
                    self.seed = int(self.seed_buf)
                self.seed_buf = None
            return
        n = len(self.ACTIONS) + len(self.options())
        if key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.menu_activate()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            self.menu_activate(-1 if key in (pygame.K_LEFT, pygame.K_a) else 1)
        elif key == pygame.K_r:
            self.seed = random_seed()
        elif key == pygame.K_F2:
            self.open_demo()
        elif key == pygame.K_ESCAPE:
            self.running = False

    def start_game(self, mode: str) -> None:
        self.session = Session(self.seed, self.size, self.bruno, mode, self.tom_algo, self.trace)
        self.paused = False
        self.notice = ""
        self.scene = "game" if self.session.state.winner is None else "end"

    def open_demo(self) -> None:
        maze = self.session.state.maze if self.session and self.scene != "menu" else \
            generate_maze(self.seed, self.size)
        self.back_scene = self.scene
        self.demo = Demo(maze, self.fonts, self.seed)
        self.scene = "demo"

    def game_key(self, key: int) -> None:
        """Game keys. In human games A and the arrows are movement; the AI overlays
        (path, explored) are spectator tools and stay off there, because they
        would show the opponent's planned route."""
        s = self.session
        assert s is not None
        if key == pygame.K_ESCAPE:
            self.scene = "menu"
        elif key == pygame.K_F2:
            self.open_demo()
        elif s.human == JERRY and key in (pygame.K_q, pygame.K_e) and not self.paused:
            kind = TRAP if key == pygame.K_q else WHISTLE
            if s.human_gadget(kind):
                self.notice = ""
            else:
                self.notice = f"{kind.title()} not available now: no turn used"
        elif s.human is not None and key in (pygame.K_TAB, pygame.K_e):
            pass  # AI plans and inputs are not shown to a human player (fair fog)
        elif key == pygame.K_TAB or key == pygame.K_a and s.human is None:
            self.overlay["path"] = not self.overlay["path"]
        elif key == pygame.K_e:
            self.overlay["explored"] = not self.overlay["explored"]
        elif key == pygame.K_t:
            s.set_trace(not s.trace)
            self.trace = s.trace
        elif key == pygame.K_p:
            self.paused = not self.paused
        elif key == pygame.K_n and s.human is None:
            s.ai_round()
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.speed = min(len(SPEEDS) - 1, self.speed + 1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.speed = max(0, self.speed - 1)
        elif key in MOVE_KEYS and s.human is not None and not self.paused:
            moved = s.human_move(MOVE_KEYS[key])
            self.notice = "" if moved else "Blocked (wall, or stunned): no turn used"
        if s.state.winner is not None:
            self.scene = "end"

    def tick(self) -> None:
        """Spectator auto-play at the chosen speed."""
        s = self.session
        if self.scene != "game" or s is None or s.human is not None or self.paused:
            return
        now = time.perf_counter()
        if now - self.last_step >= 1 / SPEEDS[self.speed]:
            self.last_step = now
            s.ai_round()
            if s.state.winner is not None:
                self.scene = "end"

    def end_choice(self, idx: int) -> None:
        mode = self.session.mode if self.session else PLAY_JERRY
        if idx == 0:
            self.start_game(mode)
        elif idx == 1:
            self.seed = random_seed()
            self.start_game(mode)
        else:
            self.scene = "menu"

    def toggle_fullscreen(self) -> None:
        """Switch between the 1280x800 window and the full screen. The canvas is always
        1280x800; SDL scales it and keeps the aspect ratio (black bars when needed)."""
        want = not self.fullscreen
        flags = pygame.SCALED | (pygame.FULLSCREEN if want else pygame.RESIZABLE)
        try:
            self.screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H), flags)
            self.fullscreen = want
        except pygame.error:  # display driver refuses the mode: stay in the window
            self.notice = "Full screen is not available on this display"

    def handle(self, ev: pygame.event.Event) -> None:
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN and (ev.key == pygame.K_F11 or (
                ev.key == pygame.K_RETURN and ev.mod & pygame.KMOD_ALT)):
            self.toggle_fullscreen()
        elif self.help:
            if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.help = False
        elif self.scene == "demo" and self.demo is not None:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.scene = self.back_scene
            else:
                self.demo.handle(ev)
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
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            hit = next((i for i, r in enumerate(self.rects) if r.collidepoint(ev.pos)), None)
            if hit is not None and self.scene == "menu" and self.seed_buf is None:
                self.selected = hit
                self.menu_activate(0 if ev.button == 1 or hit < len(self.ACTIONS) else -1)
            elif hit is not None and self.scene == "end":
                self.end_choice(hit)

    def draw(self) -> None:
        if self.scene == "demo" and self.demo is not None:
            self.demo.draw(self.screen)
        elif self.scene == "menu" or self.session is None:
            hint = ("Arrows / mouse select, Enter choose, Left / Right change, "
                    "R random seed, F2 demo, F11 full screen")
            if self.seed_buf is not None:
                hint = "Type seed digits, Enter to confirm, Esc to cancel"
            self.rects = ui.draw_menu(self.screen, self.fonts, self.ACTIONS, self.options(),
                                      self.selected, hint)
        else:
            self.draw_game(self.session)
        if self.help:
            ui.draw_help(self.screen, self.fonts)

    def draw_game(self, s: Session) -> None:
        self.screen.fill(C.COLOR_BG)
        st = s.state
        # Tom (human or AI) learns the exit only after the alarm; the game is over = all shown.
        exit_known = s.human != TOM or st.exit_open or st.winner is not None
        ai_shown = s.human is None  # AI plans, inputs and panels are for spectators only

        def overlays(g: ui.Grid) -> None:
            if not ai_shown:
                return
            for d in s.decisions.values():
                if self.overlay["explored"]:
                    ui.shade_cells(self.screen, g, d.explored, C.COLOR_EXPLORED, 70)
            for d in s.decisions.values():
                if self.overlay["path"]:
                    ui.draw_path(self.screen, g, d.path)

        ui.draw_board(self.screen, self.fonts, st, exit_known, under=overlays)
        middle = matchup(s.algos, s.human)
        if s.human:
            right = f"You: {s.human.title()}"
        else:
            right = f"x{SPEEDS[self.speed]}/s" + ("  PAUSED" if self.paused else "")
        if s.trace:
            right = f"trace {s.saved}  " + right
        ui.draw_top_bar(self.screen, self.fonts, st, middle, right)
        ais = [s.ai_view(r) for r in (TOM, JERRY) if r in s.agents] if ai_shown else []
        flags = " ".join(k for k, on in (("A", self.overlay["path"]),
                                         ("E", self.overlay["explored"]), ("T", s.trace)) if on)
        if s.human:
            keys = "Q trap, E whistle, " if s.human == JERRY else ""
            footer = [self.notice or f"WASD / arrows move, Space wait, {keys}P pause, Esc menu",
                      "T trace. AI plans stay hidden in human games; watch AI vs AI"]
        else:
            footer = ["P pause, N step, +/- speed, Tab/A path, E explored",
                      f"T trace, F2 demo, F11 full screen, Esc menu   [{flags or 'no overlays'}]"]
        ui.draw_panel(self.screen, self.fonts, ais, s.bruno_lines(), s.log, footer,
                      legend=s.human is not None)
        self.rects = []
        if self.scene == "end":
            self.rects = ui.draw_end(self.screen, self.fonts, st.winner or "", st.reason,
                                     s.stats(), END_BUTTONS)

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self.running:
            for ev in pygame.event.get():
                self.handle(ev)
            self.tick()
            if self.scene == "demo" and self.demo is not None:
                self.demo.update()
            self.draw()
            pygame.display.flip()
            clock.tick(C.FPS)


def matchup(algos: dict[str, str], human: str | None) -> str:
    """Matchup line for the top bar and end screen: the algorithm of each AI side."""
    if human is None:
        return f"Tom {LABEL[algos[TOM]]} vs Jerry {LABEL[algos[JERRY]]}"
    ai = TOM if human == JERRY else JERRY
    return f"vs AI {ai.title()} ({LABEL[algos[ai]]})"


def random_seed() -> int:
    """New seed for the menu's R key / New game. The game itself stays seeded."""
    return time.time_ns() % 1_000_000


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cheese Heist")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--size", type=int, default=C.DEFAULT_SIZE, choices=C.MAP_SIZES)
    p.add_argument("--no-bruno", action="store_true")
    p.add_argument("--tom", default="minimax", choices=[a.lower() for a in ALGORITHMS],
                   help="Tom's algorithm; Jerry's AI uses the other one")
    p.add_argument("--demo", action="store_true", help="open the algorithm demo screen")
    p.add_argument("--trace", action="store_true", help="save every AI decision trace")
    p.add_argument("--screenshot", help="start a game, play --auto rounds, save PNG, exit")
    p.add_argument("--auto", type=int, default=0, help="rounds a seeded random Jerry plays first")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    pygame.init()
    screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption(C.TITLE)
    app = App(screen, args)
    if args.screenshot:
        app.start_game(PLAY_JERRY)
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
        if args.demo:
            app.open_demo()
        app.run()
    pygame.quit()


if __name__ == "__main__":
    main()
