"""Algorithm demo screen (CLAUDE.md section 5).

Keys 1..8 pick an algorithm: 1 A*, 2 Greedy, 3 DFS, 4 DLS, 5 Bidirectional,
6 Minimax alpha-beta, 7 MCTS, 8 Fuzzy. Left click = start (Jerry), right click =
goal (Tom). Space play/pause, +/- speed, R reset, C compare A* vs greedy, Esc back
(handled by main.App). Every number comes from the same functions the agents call.
"""

from __future__ import annotations

import random

import pygame

import config as C
import minimax
import ui
from agents import TomAgent, evade_plan
from fuzzy import FuzzyResult, FuzzySystem, JerryController, TomController
from game import TOM, make_observation, new_game
from maze import Maze
from mcts import MCTSResult, mcts, opponent_cells
from search import (
    BidirResult,
    Cell,
    DLSResult,
    SearchResult,
    astar,
    bidirectional_bfs,
    dfs,
    dls,
    greedy_best_first,
)

ALGOS = {1: "A*", 2: "Greedy best-first", 3: "DFS", 4: "Depth-limited (DLS)",
         5: "Bidirectional BFS", 6: "Minimax alpha-beta", 7: "MCTS", 8: "Fuzzy logic"}
SPEEDS = (5, 10, 20, 40, 80, 160)  # animation cells per second
YELLOW, MAGENTA, RED = (0xF4, 0xD0, 0x3F), (0xE0, 0x40, 0xFB), (0xE7, 0x4C, 0x3C)
ORANGE = (0xF3, 0x8B, 0x2A)
PANEL = pygame.Rect(C.PANEL_X, C.TOP_BAR_H, C.PANEL_W, C.WINDOW_H - C.TOP_BAR_H)


def frontier(maze: Maze, expanded: list[Cell]) -> list[Cell]:
    """Generated-but-not-expanded cells after `expanded` (exact for BFS/DFS/A*/greedy:
    each expands every free neighbour)."""
    done = set(expanded)
    return list(dict.fromkeys(n for c in expanded for n in maze.adj[c] if n not in done))


class Demo:
    """State of the demo screen. `update` advances the animation, `draw` renders."""

    def __init__(self, maze: Maze, fonts: ui.Fonts, seed: int) -> None:
        self.maze, self.fonts, self.seed = maze, fonts, seed
        self.algo = 1
        self.start, self.goal = maze.jerry_start, maze.tom_start
        self.speed = 2
        self.playing = True
        self.progress = 0.0
        self.compare = False
        self.dls_limit = C.DLS_DEPTH
        self.mcts_age = 3
        self.controllers: dict[str, FuzzySystem] = {"TOM": TomController(),
                                                    "JERRY": JerryController()}
        self.fz_role = "TOM"
        self.fz_inputs = {"TOM": {"dist": 6.0, "age": 2.0, "bruno": 0.0},
                          "JERRY": {"danger": 5.0, "keys_left": 2.0, "bruno_ready": 1.0}}
        self.fz_sel = 0
        self.compute()

    # ---------------------------------------------------------- model
    def compute(self) -> None:
        """Run the selected algorithm on the current start/goal (with traces)."""
        m, s, g = self.maze, self.start, self.goal
        self.progress = 0.0
        self.res: SearchResult | None = None
        self.res2: SearchResult | None = None
        self.order: list[Cell] = []
        if self.compare:
            self.res = astar(m.adj, s, g, trace=True)
            self.res2 = greedy_best_first(m.adj, s, g, trace=True)
            self.order = self.res.explored_order
        elif self.algo == 1:
            self.res = astar(m.adj, s, g, trace=True)
        elif self.algo == 2:
            self.res = greedy_best_first(m.adj, s, g, trace=True)
        elif self.algo == 3:
            self.res = dfs(m.adj, s, g, trace=True)
        elif self.algo == 4:
            self.dls_res: DLSResult = dls(m.adj, s, lambda c: c == g, self.dls_limit)
            self.evade = evade_plan(m, s, g)
            self.order = self.dls_res.explored_order
        elif self.algo == 5:
            self.bidir: BidirResult = bidirectional_bfs(m.adj, s, g, trace=True)
            dist_s, dist_g = m.dist_map(s), m.dist_map(g)
            fwd = [(2 * dist_s[c], 0, c) for c in self.bidir.forward_order]
            bwd = [(2 * dist_g[c] + 1, 1, c) for c in self.bidir.backward_order]
            # layers alternate forward, backward, forward ... exactly as the search ran
            self.bidir_seq = [(side, c) for _, side, c in sorted(fwd + bwd, key=lambda t: t[0])]
            self.order = [c for _, c in self.bidir_seq]
        elif self.algo == 6:
            state = new_game(m)
            state.jerry, state.tom = s, g
            state.keys = tuple(k for k in state.keys if k != s)
            state.last_seen = {"JERRY": None, "TOM": None}
            self.mm = minimax.decide(state, TOM, trace=True)
        elif self.algo == 7:
            state = new_game(m)
            state.jerry, state.tom, state.turn = s, g, 10
            obs = make_observation(state, TOM)
            tom = TomAgent("NIGHTMARE", self.seed)
            tom.last_seen = (s, state.turn - self.mcts_age)
            self.mcts_targets = tom.mcts_targets(obs)
            self.mcts_cells = opponent_cells(obs, tom.last_seen)
            self.mc: MCTSResult = mcts(obs, self.mcts_targets, self.mcts_cells,
                                       random.Random(self.seed), trace=True)
        if self.res is not None and not self.order:
            self.order = self.res.explored_order

    def fuzzy(self) -> tuple[FuzzySystem, dict[str, float], FuzzyResult]:
        system = self.controllers[self.fz_role]
        inputs = self.fz_inputs[self.fz_role]
        return system, inputs, system.evaluate(inputs, trace=True)

    # ---------------------------------------------------------- input
    def handle(self, ev: pygame.event.Event) -> None:
        if ev.type == pygame.KEYDOWN:
            self.key(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3) and not self.compare:
            cell = self.geometry().cell_at(ev.pos, self.maze)
            if cell is not None and self.algo != 8:
                if ev.button == 1:
                    self.start = cell
                else:
                    self.goal = cell
                self.compute()

    def geometry(self) -> ui.Geometry:
        """Where the clickable map is: a small map under the minimax tree, else the board."""
        if self.algo == 6 and not self.compare:
            return ui.board_geometry(self.maze, pygame.Rect(16, 420, 290, 290))
        return ui.board_geometry(self.maze)

    def key(self, key: int) -> None:
        num = {getattr(pygame, f"K_{i}"): i for i in range(1, 9)}
        num.update({getattr(pygame, f"K_KP{i}"): i for i in range(1, 9)})
        if key in num:
            self.algo, self.compare = num[key], False
            self.compute()
        elif key == pygame.K_SPACE:
            self.playing = not self.playing
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.speed = min(len(SPEEDS) - 1, self.speed + 1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.speed = max(0, self.speed - 1)
        elif key == pygame.K_r:
            self.progress = 0.0
            self.playing = True
        elif key == pygame.K_c:
            self.compare = not self.compare
            self.compute()
        elif key == pygame.K_TAB and self.algo == 8:
            self.fz_role = "JERRY" if self.fz_role == "TOM" else "TOM"
            self.fz_sel = 0
        elif key in (pygame.K_UP, pygame.K_DOWN):
            self.adjust(-1 if key == pygame.K_UP else 1, vertical=True)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.adjust(-1 if key == pygame.K_LEFT else 1, vertical=False)

    def adjust(self, d: int, vertical: bool) -> None:
        """Up/Down: DLS depth limit, MCTS sighting age, fuzzy input selection.
        Left/Right: fuzzy slider value."""
        if self.algo == 4 and vertical:
            self.dls_limit = max(1, self.dls_limit - d)
            self.compute()
        elif self.algo == 7 and vertical:
            self.mcts_age = max(0, self.mcts_age - d)
            self.compute()
        elif self.algo == 8:
            system = self.controllers[self.fz_role]
            names = list(system.inputs)
            if vertical:
                self.fz_sel = (self.fz_sel + d) % len(names)
            else:
                var = system.inputs[names[self.fz_sel]]
                step = (var.hi - var.lo) / (30 if var.hi > 3 else 20)
                cur = self.fz_inputs[self.fz_role][var.name]
                self.fz_inputs[self.fz_role][var.name] = round(
                    min(var.hi, max(var.lo, cur + d * step)), 3)

    def update(self) -> None:
        if self.playing:
            self.progress += SPEEDS[self.speed] / C.FPS

    def shown(self) -> int:
        return min(len(self.order), int(self.progress))

    # ---------------------------------------------------------- drawing
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(C.COLOR_BG)
        pygame.draw.rect(surf, C.COLOR_PANEL, (0, 0, C.WINDOW_W, C.TOP_BAR_H))
        name = "Compare A* vs greedy" if self.compare else ALGOS[self.algo]
        ui.text(surf, self.fonts.big, f"Algorithm demo: {name}", (14, 12))
        ui.text(surf, self.fonts.small, "1 A*  2 Greedy  3 DFS  4 DLS  5 Bidir  6 Minimax  "
                "7 MCTS  8 Fuzzy   C compare   Esc back", (C.WINDOW_W - 14, 17),
                C.COLOR_TEXT_DIM, right=True)
        if self.compare:
            self.draw_compare(surf)
        elif self.algo in (1, 2, 3, 4, 5):
            self.draw_search(surf)
        elif self.algo == 6:
            self.draw_minimax(surf)
        elif self.algo == 7:
            self.draw_mcts(surf)
        else:
            self.draw_fuzzy(surf)

    def panel(self, surf: pygame.Surface, lines: list[tuple[str, str]], y: int = 0) -> int:
        """Right panel: label/value rows. Returns next y."""
        if y == 0:
            pygame.draw.rect(surf, C.COLOR_PANEL, PANEL)
            pygame.draw.line(surf, C.COLOR_PANEL_LINE, PANEL.topleft, PANEL.bottomleft)
            y = PANEL.y + 14
        x = PANEL.x + 18
        for label, value in lines:
            if label == "#":  # section heading
                ui.text(surf, self.fonts.tiny, value.upper(), (x, y + 4), C.COLOR_TEXT_DIM)
                y += 22
            elif label:
                ui.text(surf, self.fonts.small, label, (x, y), C.COLOR_TEXT_DIM)
                ui.text(surf, self.fonts.normal, ui.fit(self.fonts.normal, value, 230),
                        (x + 160, y - 2))
                y += 24
            else:
                ui.text(surf, self.fonts.small, ui.fit(self.fonts.small, value, PANEL.w - 36),
                        (x, y))
                y += 20
        return y

    def markers(self, surf: pygame.Surface, g: ui.Geometry, start_label: str = "S",
                goal_label: str = "G") -> None:
        for cell, label, color in ((self.start, start_label, C.COLOR_ACCENT),
                                   (self.goal, goal_label, RED)):
            pygame.draw.circle(surf, color, g.center(cell), g.tile // 2 - 2, 3)
            ui.text(surf, self.fonts.small, label, g.center(cell), C.COLOR_TEXT, center=True)

    def draw_progress(self, surf: pygame.Surface, g: ui.Geometry, res: SearchResult,
                      k: int) -> None:
        """Explored (blue), frontier (yellow), final path (green) after k expansions."""
        done = res.explored_order[:k]
        ui.shade_cells(surf, g, done, C.COLOR_EXPLORED, 110)
        if k < len(res.explored_order):
            ui.shade_cells(surf, g, frontier(self.maze, done), YELLOW, 120)
        else:
            ui.draw_path(surf, g, res.path)

    def draw_search(self, surf: pygame.Surface) -> None:
        g = ui.board_geometry(self.maze)
        ui.draw_maze(surf, self.maze, g)
        k = self.shown()
        finished = k >= len(self.order)
        lines: list[tuple[str, str]] = [("#", ALGOS[self.algo])]
        if self.algo in (1, 2, 3):
            assert self.res is not None
            self.draw_progress(surf, g, self.res, k)
            lines += [("Nodes expanded", f"{k} / {self.res.nodes_expanded}"),
                      ("Path length", str(len(self.res.path) - 1) if finished else "..."),
                      ("Time", f"{self.res.ms:.3f} ms")]
            steps = (self.res.trace or {}).get("steps", [])
            if self.algo in (1, 2) and steps:
                st = steps[max(0, min(k, len(steps)) - 1)]
                lines += [("#", f"expansion {st['n']}"), ("Cell", str(tuple(st["expand"]))),
                          ("g / h / f", f"{st['g']:g} / {st['h']} / {st['f']:g}"),
                          ("Open list", f"{st['open_size']} cells"),
                          ("", "top: " + "  ".join(f"{tuple(c)} f={f:g}"
                                                   for c, f in st["open_top"][:3]))]
        elif self.algo == 4:
            r = self.dls_res
            done = r.explored_order[:k]
            ui.shade_cells(surf, g, done, C.COLOR_EXPLORED, 110)
            if finished:
                ui.shade_cells(surf, g, r.cutoff_cells, RED, 150)
                ui.draw_path(surf, g, r.path)
                ui.draw_path(surf, g, self.evade.best_path, MAGENTA)
            ev = self.evade.trace
            lines += [("Depth limit", f"{self.dls_limit}  (Up/Down)"),
                      ("Status", r.status if finished else "..."),
                      ("Nodes", f"{k} / {r.nodes_expanded}"),
                      ("Cutoff cells", f"{len(r.cutoff_cells)} (red)"),
                      ("#", "Jerry EVADE: dls_safe_paths, Tom at G"),
                      ("Paths of 5 steps", str(ev["paths_enumerated"])),
                      ("Safe paths", str(ev["safe_paths"])),
                      ("Cutoff / dead end", f"{ev['cutoffs']} / {ev['dead_ends']}"),
                      ("Best score", f"{ev['best_score']:.1f}" if ev["best_score"] is not None
                       else "none: flee"),
                      ("", "best safe path in magenta")]
        else:
            b = self.bidir
            fwd = [c for side, c in self.bidir_seq[:k] if side == 0]
            bwd = [c for side, c in self.bidir_seq[:k] if side == 1]
            ui.shade_cells(surf, g, fwd, C.COLOR_EXPLORED, 120)
            ui.shade_cells(surf, g, bwd, ORANGE, 120)
            if finished:
                ui.draw_path(surf, g, b.path)
                if b.meeting is not None:
                    ui.shade_cells(surf, g, [b.meeting], MAGENTA, 220)
            else:
                ui.shade_cells(surf, g, frontier(self.maze, fwd), C.COLOR_EXPLORED, 60)
                ui.shade_cells(surf, g, frontier(self.maze, bwd), ORANGE, 60)
            lines += [("Nodes", f"{k} / {b.nodes_expanded}"),
                      ("Fwd / bwd nodes", f"{len(b.forward_order)} / {len(b.backward_order)}"),
                      ("Meeting cell", str(b.meeting) if finished else "..."),
                      ("Path length", str(len(b.path) - 1) if finished else "..."),
                      ("Time", f"{b.ms:.3f} ms"),
                      ("", "forward wave blue, backward orange, meeting magenta")]
        self.markers(surf, g)
        lines += [("#", "controls"), ("", "Left click start S, right click goal G"),
                  ("", f"Space {'pause' if self.playing else 'play'}, +/- speed "
                       f"({SPEEDS[self.speed]} cells/s), R reset")]
        self.panel(surf, lines)
        if self.algo == 5:
            keys = [(C.COLOR_EXPLORED, "forward"), (ORANGE, "backward"), (MAGENTA, "meeting"),
                    (C.COLOR_PATH, "path")]
        elif self.algo == 4:
            keys = [(C.COLOR_EXPLORED, "explored"), (RED, "cutoff"), (C.COLOR_PATH, "path"),
                    (MAGENTA, "evade path")]
        else:
            keys = [(C.COLOR_EXPLORED, "explored"), (YELLOW, "frontier"), (C.COLOR_PATH, "path")]
        self.legend(surf, keys)

    def legend(self, surf: pygame.Surface, keys: list[tuple[ui.Color, str]]) -> None:
        x, y = PANEL.x + 18, C.WINDOW_H - 34
        for color, label in keys:
            pygame.draw.rect(surf, color, (x, y + 2, 14, 14))
            x = ui.text(surf, self.fonts.small, label, (x + 20, y)).right + 16

    def draw_compare(self, surf: pygame.Surface) -> None:
        assert self.res is not None and self.res2 is not None
        k = int(self.progress)
        rows = []
        for i, (res, label) in enumerate(((self.res, "A*"), (self.res2, "Greedy best-first"))):
            area = pygame.Rect(8 + i * 546, C.TOP_BAR_H + 28, 538, 538)
            g = ui.board_geometry(self.maze, area)
            ui.text(surf, self.fonts.normal, label, (area.x, C.TOP_BAR_H + 6))
            ui.draw_maze(surf, self.maze, g)
            self.draw_progress(surf, g, res, min(k, len(res.explored_order)))
            self.markers(surf, g)
            rows.append((label, res))
        y0 = C.TOP_BAR_H + 576
        cols = (20, 260, 440, 620, 800)
        for x, head in zip(cols, ("Algorithm", "Nodes expanded", "Path length", "Time ms",
                                  "Optimal?"), strict=True):
            ui.text(surf, self.fonts.small, head, (x, y0), C.COLOR_TEXT_DIM)
        best = len(self.res.path) - 1
        for j, (label, res) in enumerate(rows):
            y = y0 + 26 + j * 26
            plen = len(res.path) - 1
            vals = (label, str(res.nodes_expanded), str(plen), f"{res.ms:.3f}",
                    "yes" if plen == best else f"no (+{plen - best})")
            for x, v in zip(cols, vals, strict=True):
                ui.text(surf, self.fonts.normal, v, (x, y))
        ui.text(surf, self.fonts.small, "Same maze, start and goal.  C back, Space pause, R replay",
                (C.WINDOW_W - 20, C.WINDOW_H - 22), C.COLOR_TEXT_DIM, right=True)

    # ---- minimax tree
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
        for n in tree:
            if n["parent"] is None:
                continue
            a, b = pos[n["parent"]], pos[n["id"]]
            hot = n["id"] == chosen
            color = C.COLOR_PATH if hot else ((70, 76, 90) if n["pruned"] else C.COLOR_PANEL_LINE)
            pygame.draw.line(surf, color, a, b, 4 if hot else 2)
            mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            ui.text(surf, self.fonts.tiny, (n["move"] or "")[:1], (mx + 6, my - 8),
                    C.COLOR_TEXT_DIM)
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
            ui.text(surf, font, val, (x, y + r + 8), C.COLOR_TEXT_DIM if n["pruned"]
                    else C.COLOR_TEXT, center=True)
            if n["ply"] < 2 and not n["pruned"]:
                ui.text(surf, self.fonts.tiny, f"a={_short(n['alpha'])} b={_short(n['beta'])}",
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

    # ---- MCTS
    def draw_mcts(self, surf: pygame.Surface) -> None:
        g = ui.board_geometry(self.maze)
        ui.draw_maze(surf, self.maze, g)
        mc = self.mc
        top = max(mc.samples.values(), default=1)
        for cell, n in mc.samples.items():
            pygame.draw.circle(surf, MAGENTA, g.center(cell), max(2, int(g.tile * 0.3 * n / top)))
        for k in self.maze.keys:
            ui.draw_key(surf, g.center(k), g.tile)
        ui.draw_kennel(surf, g.center(self.maze.kennel), g.tile)
        letters = {}
        for i, child in enumerate(mc.children):
            letters[child.target] = chr(65 + i)
            rect = g.rect(child.target)
            color = C.COLOR_PATH if child.target == mc.target else C.COLOR_CHEESE
            pygame.draw.rect(surf, color, rect, 3)
            ui.text(surf, self.fonts.small, letters[child.target], (rect.x + 2, rect.y + 1),
                    color)
        ui.draw_jerry(surf, g.center(self.start), g.tile)
        ui.draw_tom(surf, g.center(self.goal), g.tile, 0)
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
        self.panel(surf, [("#", "controls"), ("", "Left click Jerry's last seen cell,"),
                          ("", "right click Tom. Re-runs 300 iterations.")], y)

    # ---- fuzzy sliders
    def draw_fuzzy(self, surf: pygame.Surface) -> None:
        system, inputs, res = self.fuzzy()
        names = list(system.inputs)
        ui.draw_fuzzy_view(surf, self.fonts, pygame.Rect(0, C.TOP_BAR_H, C.BOARD_PX, C.BOARD_PX),
                           system, inputs, res, names[self.fz_sel])
        lines: list[tuple[str, str]] = [("#", f"{system.role.title()} inputs (Tab: other side)")]
        y = self.panel(surf, lines)
        x = PANEL.x + 18
        for i, name in enumerate(names):
            var = system.inputs[name]
            sel = i == self.fz_sel
            ui.text(surf, self.fonts.normal, f"{name} = {inputs[name]:g}", (x, y),
                    C.COLOR_CHEESE if sel else C.COLOR_TEXT)
            track = pygame.Rect(x, y + 26, PANEL.w - 36, 6)
            pygame.draw.rect(surf, C.COLOR_PANEL_LINE, track, border_radius=3)
            kx = track.x + int((inputs[name] - var.lo) / (var.hi - var.lo) * track.w)
            pygame.draw.circle(surf, C.COLOR_CHEESE if sel else C.COLOR_ACCENT,
                               (kx, track.centery), 8)
            y += 52
        y = self.panel(surf, [("#", "result"), ("Centroid", f"{res.centroid:.2f}"),
                              ("Mode", res.mode)], y + 4)
        y = ui.fuzzy_bars(surf, self.fonts, x, y + 4, PANEL.w - 36, res)
        self.panel(surf, [("#", "controls"), ("", "Up/Down pick input, Left/Right change it"),
                          ("", "Tab: Tom / Jerry controller")], y + 8)


def _short(v: float | str) -> str:
    return v if isinstance(v, str) else f"{v:g}"
