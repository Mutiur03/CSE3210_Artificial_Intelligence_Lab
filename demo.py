"""Algorithm demo screen (CLAUDE.md section 5).

Keys 1..2 pick an algorithm: 1 Minimax alpha-beta, 2 MCTS. Left click = Jerry's
cell (S), right click = Tom's cell (G). Up/Down change the MCTS sighting age.
Esc back (handled by main.App). Every number comes from the same functions the
agents call.
"""

from __future__ import annotations

import random

import pygame

import config as C
import minimax
import render3d
import ui
from agents import MCTS, AIAgent
from game import TOM, GameState, make_observation, new_game
from maze import Maze
from mcts import MCTSResult, mcts, opponent_cells

ALGOS = {1: "Minimax alpha-beta", 2: "MCTS"}
MAGENTA = (0xE0, 0x40, 0xFB)
PANEL = pygame.Rect(C.PANEL_X, C.TOP_BAR_H, C.PANEL_W, C.WINDOW_H - C.TOP_BAR_H)


class Demo:
    """State of the demo screen. `draw` renders the selected algorithm's result."""

    def __init__(self, maze: Maze, fonts: ui.Fonts, seed: int) -> None:
        self.maze, self.fonts, self.seed = maze, fonts, seed
        self.algo = 1
        self.start, self.goal = maze.jerry_start, maze.tom_start
        self.mcts_age = 3
        self.mcts_iters = C.MCTS_ITERATIONS
        self.reveal: int | None = None  # minimax: nodes shown so far (None = whole tree)
        self.caption = ""  # situation text for videos, shown in the top bar
        self.scene: GameState | None = None
        self.compute()

    def compute(self) -> None:
        """Run the selected algorithm on the current Jerry (S) / Tom (G) cells."""
        m, s, g = self.maze, self.start, self.goal
        self.scene = None
        if self.algo == 1:
            state = new_game(m)
            state.jerry, state.tom = s, g
            state.keys = tuple(k for k in state.keys if k != s)
            state.last_seen = {"JERRY": None, "TOM": None}
            self.mm = minimax.decide(state, TOM, trace=True)
        else:
            state = new_game(m)
            state.jerry, state.tom, state.turn = s, g, 10
            obs = make_observation(state, TOM)
            tom = AIAgent(TOM, MCTS, self.seed)
            tom.last_seen = (s, state.turn - self.mcts_age)
            self.mcts_targets = tom.mcts_targets(obs)
            self.mcts_cells = opponent_cells(obs, tom.last_seen)
            self.mc: MCTSResult = mcts(obs, self.mcts_targets, self.mcts_cells,
                                       random.Random(self.seed), self.mcts_iters, trace=True)

    def handle(self, ev: pygame.event.Event) -> None:
        if ev.type == pygame.KEYDOWN:
            self.key(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            cell = self.geometry().cell_at(ev.pos, self.maze)
            if cell is not None:
                if ev.button == 1:
                    self.start = cell
                else:
                    self.goal = cell
                self.compute()

    def geometry(self) -> ui.Geometry:
        """Where the clickable map is: a small map under the minimax tree, else the board."""
        if self.algo == 1:
            return ui.board_geometry(self.maze, pygame.Rect(16, 420, 290, 290))
        return ui.board_geometry(self.maze)

    def key(self, key: int) -> None:
        num = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_KP1: 1, pygame.K_KP2: 2}
        if key in num:
            self.algo = num[key]
            self.compute()
        elif self.algo == 2 and key in (pygame.K_UP, pygame.K_DOWN):
            self.mcts_age = max(0, self.mcts_age + (1 if key == pygame.K_UP else -1))
            self.compute()

    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(C.COLOR_BG)
        pygame.draw.rect(surf, C.COLOR_PANEL, (0, 0, C.WINDOW_W, C.TOP_BAR_H))
        name = ALGOS[self.algo]
        ui.text(surf, self.fonts.big, f"Algorithm demo: {name}", (14, 12))
        hint = self.caption or "1 Minimax alpha-beta   2 MCTS   Esc back"
        room = C.WINDOW_W - 28 - 20 - self.fonts.big.size(f"Algorithm demo: {name}")[0]
        ui.text(surf, self.fonts.small, ui.fit(self.fonts.small, hint, room), (C.WINDOW_W - 14, 17),
                C.COLOR_TEXT_DIM, right=True)
        if self.algo == 1:
            self.draw_minimax(surf)
        else:
            self.draw_mcts(surf)

    def panel(self, surf: pygame.Surface, lines: list[tuple[str, str]], y: int = 0) -> int:
        """Right panel: label/value rows. Returns next y."""
        if y == 0:
            pygame.draw.rect(surf, C.COLOR_PANEL, PANEL)
            pygame.draw.line(surf, C.COLOR_PANEL_LINE, PANEL.topleft, PANEL.bottomleft)
            y = PANEL.y + 14
        x = PANEL.x + 18
        for label, value in lines:
            if label == "#":  # section heading
                ui.text(surf, self.fonts.small, value, (x, y + 2), C.COLOR_ACCENT)
                y += 22
            elif label:
                ui.text(surf, self.fonts.small, label, (x, y), C.COLOR_TEXT_DIM)
                ui.text(surf, self.fonts.normal, ui.fit(self.fonts.normal, value, PANEL.w - 196),
                        (x + 160, y - 2))
                y += 24
            else:
                ui.text(surf, self.fonts.small, ui.fit(self.fonts.small, value, PANEL.w - 36),
                        (x, y))
                y += 20
        return y

    def board(self, surf: pygame.Surface) -> ui.Grid:
        """Draw the maze (3D scene with Jerry at S and Tom at G, flat 2D if there is no GL)
        and return the grid the overlays draw on."""
        r3d = render3d.get_renderer()
        if r3d is None:
            g = ui.board_geometry(self.maze)
            ui.draw_maze(surf, self.maze, g)
            return g
        if self.scene is None:
            self.scene = new_game(self.maze, bruno_enabled=False)
            self.scene.tom, self.scene.jerry = self.goal, self.start
        surf.blit(r3d.render(self.scene, True), (C.BOARD_X, C.BOARD_Y))
        ui.draw_tags(surf, self.fonts, r3d)
        return r3d.grid

    def draw_minimax(self, surf: pygame.Surface) -> None:
        tr = self.mm.trace or {}
        tree = [n for n in tr.get("tree", []) if n["ply"] <= 2][:40]
        by_parent: dict[int | None, list[dict]] = {}
        for n in tree:
            by_parent.setdefault(n["parent"], []).append(n)
        leaves: list[dict] = []

        def collect(n: dict) -> None:
            kids = by_parent.get(n["id"], [])
            if not kids:
                leaves.append(n)
            for kid in kids:
                collect(kid)

        root = tree[0]
        collect(root)
        pos: dict[int, tuple[int, int]] = {}
        span = (C.WINDOW_W - 40) / max(1, len(leaves))
        for i, n in enumerate(leaves):
            pos[n["id"]] = (int(20 + span * (i + 0.5)), 0)

        def place(n: dict) -> int:
            kids = by_parent.get(n["id"], [])
            if kids:
                xs = [place(k) for k in kids]
                pos[n["id"]] = ((xs[0] + xs[-1]) // 2, 0)
            return pos[n["id"]][0]

        place(root)
        ys = {0: 92, 1: 210, 2: 340}
        chosen = next((n["id"] for n in by_parent.get(0, []) if n["move"] == self.mm.action), None)
        for n in tree:
            x, _ = pos[n["id"]]
            pos[n["id"]] = (x, ys[n["ply"]])
        shown = {n["id"] for n in tree[:self.reveal]}
        tree = [n for n in tree if n["id"] in shown]
        for n in tree:
            if n["parent"] is None:
                continue
            a, b = pos[n["parent"]], pos[n["id"]]
            hot = n["id"] == chosen
            color = C.COLOR_PATH if hot else ((70, 76, 90) if n["pruned"] else C.COLOR_PANEL_LINE)
            pygame.draw.line(surf, color, a, b, 4 if hot else 2)
            mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            ui.text_box(surf, self.fonts.tiny, (n["move"] or "")[:1], (mx + 10, my),
                        C.COLOR_TEXT_DIM, center=True)
        for n in tree:
            x, y = pos[n["id"]]
            r = 18 if n["ply"] < 2 else 12
            if n["pruned"]:
                color = (70, 76, 90)
            else:
                color = C.COLOR_TOM if n["player"] == TOM else C.COLOR_JERRY
            pts = ([(x, y - r), (x - r, y + r - 4), (x + r, y + r - 4)] if n["player"] == TOM
                   else [(x, y + r), (x - r, y - r + 4), (x + r, y - r + 4)])
            pygame.draw.polygon(surf, color, pts)
            val = "pruned" if n["pruned"] else f"{n['value']:g}"
            font = self.fonts.small if n["ply"] < 2 else self.fonts.tiny
            ui.text_box(surf, font, val, (x, y + r + 8), C.COLOR_TEXT_DIM if n["pruned"]
                        else C.COLOR_TEXT, center=True)
            if n["ply"] < 2 and not n["pruned"]:
                ui.text_box(surf, self.fonts.tiny,
                            f"a={_short(n['alpha'])} b={_short(n['beta'])}",
                            (x, y + r + 24), C.COLOR_TEXT_DIM, center=True)
        ui.text(surf, self.fonts.small, "Tom = MAX (triangle up), Jerry = MIN (triangle down). "
                "Top 3 levels of the depth-4 alpha-beta tree; grey = pruned; green = chosen.",
                (20, 60), C.COLOR_TEXT_DIM)
        g = self.geometry()
        ui.draw_maze(surf, self.maze, g)
        ui.draw_path(surf, g, [self.goal] + [p[2] for p in self.mm.pv if p[0] == TOM])
        ui.draw_jerry(surf, g.center(self.start), g.tile)
        ui.draw_tom(surf, g.center(self.goal), g.tile, 0)
        terms = (tr.get("tree") or [{}])[0].get("eval_terms") or {}
        x = 330
        rows = [f"Chosen move: {self.mm.action}   value {self.mm.value:g}",
                f"Depth reached {self.mm.depth}, nodes {self.mm.nodes}, {self.mm.ms:.1f} ms",
                "Principal variation: " + " ".join(f"{p[0][0]}:{p[1]}" for p in self.mm.pv),
                "Leaf at the end of it (evaluation terms):",
                "  " + ", ".join(f"{k}={v}" for k, v in terms.items()),
                f"E = {C.W_DIST}*dist + {C.W_GOAL}*goal + {C.W_ESCAPE}*escape "
                f"+ {C.W_BRUNO_NEAR}*bruno_near + {C.W_STUN}*stun + {C.W_DEAD_END}*dead_end",
                "Capture = +1000 - ply, escape = -1000 + ply (Tom's view).",
                "Left click = Jerry cell, right click = Tom cell on the small map.",
                "Green line on the map = Tom's moves along the principal variation."]
        for i, row in enumerate(rows):
            ui.text(surf, self.fonts.small, ui.fit(self.fonts.small, row, C.WINDOW_W - x - 20),
                    (x, 436 + i * 28), C.COLOR_TEXT if i < 5 else C.COLOR_TEXT_DIM)

    def draw_mcts(self, surf: pygame.Surface) -> None:
        g = self.board(surf)
        mc = self.mc
        top = max(mc.samples.values(), default=1)
        for cell, n in mc.samples.items():
            pygame.draw.circle(surf, MAGENTA, g.center(cell), max(2, int(g.tile * 0.3 * n / top)))
        letters = {}
        for i, child in enumerate(mc.children):
            letters[child.target] = chr(65 + i)
            quad = g.quad(child.target)
            color = C.COLOR_PATH if child.target == mc.target else C.COLOR_CHEESE
            pygame.draw.polygon(surf, color, quad, 3)
            ui.text(surf, self.fonts.small, letters[child.target], quad[0], color)
        lines: list[tuple[str, str]] = [
            ("#", "information-set UCT, Tom picks an ambush target"),
            ("Iterations", f"{mc.iterations}  ({mc.ms:.0f} ms)"),
            ("Sighting age", f"{self.mcts_age}  (Up/Down)"),
            ("Sampled cells", f"{len(self.mcts_cells)} (magenta dots)"),
            ("Chosen", f"{letters[mc.target]} {mc.target}"),
            ("#", "visits per target (bar), win rate, UCB")]
        y = self.panel(surf, lines)
        x = PANEL.x + 18
        most = max(c.visits for c in mc.children) or 1
        n_root = sum(c.visits for c in mc.children)
        for child in mc.children:
            label = f"{letters[child.target]} {child.target}"
            kind = ("key" if child.target in self.maze.keys else
                    "kennel" if child.target == self.maze.kennel else "last seen")
            ui.text(surf, self.fonts.small, f"{label} {kind}", (x, y))
            bar = pygame.Rect(x, y + 20, int((PANEL.w - 36) * child.visits / most), 10)
            pygame.draw.rect(surf, C.COLOR_PATH if child.target == mc.target else C.COLOR_ACCENT,
                             bar, border_radius=3)
            wr = child.wins / child.visits if child.visits else 0
            ui.text(surf, self.fonts.tiny, f"{child.visits} visits  win {wr:.2f}  "
                    f"UCB {child.ucb(n_root, C.MCTS_UCB_C):.2f}", (x + 150, y + 2),
                    C.COLOR_TEXT_DIM)
            y += 40
        help_lines = [("#", "controls"), ("", "Left click Jerry's last seen cell,"),
                      ("", "right click Tom. Re-runs 300 iterations.")]
        if not any(child.wins for child in mc.children):
            help_lines += [("#", "why every win rate is 0"),
                           ("", "No 20-turn playout let Tom catch Jerry: he is too"),
                           ("", "far. Right-click Tom closer to see the bars differ.")]
        self.panel(surf, help_lines, y)



def _short(v: float | str) -> str:
    return v if isinstance(v, str) else f"{v:g}"
