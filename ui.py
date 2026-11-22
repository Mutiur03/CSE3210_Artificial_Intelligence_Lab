"""Pygame drawing: board, characters, fog, overlays, top bar, right panel, fuzzy
view, menu, help and end screens.

Pure drawing. No game rules here; everything shown comes from GameState,
Decision and FuzzyResult objects passed in by main.py / demo.py.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pygame

import config as C
import render3d
from fuzzy import FuzzyResult, FuzzySystem
from game import JERRY, SLEEP, TOM, GameState
from maze import Maze
from search import Cell

Color = tuple[int, int, int]
DARK_TEXT = (15, 18, 25)
MODE_COLORS = {
    "HUNT": (0xE7, 0x4C, 0x3C), "AMBUSH": (0xE6, 0x7E, 0x22), "SWEEP": (0xF1, 0xC4, 0x0F),
    "RETREAT": (0x95, 0xA5, 0xA6), "SNEAK": (0x5D, 0xAD, 0xE2), "EVADE": (0xAF, 0x7A, 0xC5),
    "RUN_FOR_BRUNO": (0xA1, 0x88, 0x7F), "BRUNO": (0xA1, 0x88, 0x7F),
    "DASH": (0x2E, 0xCC, 0x71), "SCRIPTED": (0x7F, 0x8C, 0x8D),
}
ROLE_COLORS = {TOM: C.COLOR_TOM, JERRY: C.COLOR_JERRY}


def ui_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Installed system face from C.FONT_NAMES (no font files shipped); pygame default if none."""
    return pygame.font.SysFont(",".join(C.FONT_NAMES), size, bold=bold)


@dataclass
class Fonts:
    """UI type scale, sized for the 1280x800 canvas. Headings are bold, body is regular."""

    tiny: pygame.font.Font = field(default_factory=lambda: ui_font(15))
    small: pygame.font.Font = field(default_factory=lambda: ui_font(18))
    normal: pygame.font.Font = field(default_factory=lambda: ui_font(21))
    big: pygame.font.Font = field(default_factory=lambda: ui_font(28, bold=True))
    title: pygame.font.Font = field(default_factory=lambda: ui_font(64, bold=True))


def text(surf: pygame.Surface, font: pygame.font.Font, s: str, pos: tuple[int, int],
         color: Color = C.COLOR_TEXT, center: bool = False, right: bool = False) -> pygame.Rect:
    img = font.render(s, True, color)
    if center:
        rect = img.get_rect(center=pos)
    elif right:
        rect = img.get_rect(topright=pos)
    else:
        rect = img.get_rect(topleft=pos)
    surf.blit(img, rect)
    return rect


def fit(font: pygame.font.Font, s: str, width: int) -> str:
    """Cut `s` with '..' so it renders within `width` pixels."""
    if font.size(s)[0] <= width:
        return s
    while s and font.size(s + "..")[0] > width:
        s = s[:-1]
    return s + ".."


def chip(surf: pygame.Surface, font: pygame.font.Font, label: str, pos: tuple[int, int],
         color: Color) -> pygame.Rect:
    """Rounded label ('mode chip')."""
    w, h = font.size(label)
    rect = pygame.Rect(pos[0], pos[1], w + 18, h + 8)
    pygame.draw.rect(surf, color, rect, border_radius=rect.h // 2)
    text(surf, font, label, rect.center, DARK_TEXT, center=True)
    return rect


# ------------------------------------------------------------------ board


@dataclass(frozen=True)
class Geometry:
    """Where a maze is drawn: tile size and top-left pixel."""

    tile: int
    ox: int
    oy: int

    def center(self, cell: Cell) -> tuple[int, int]:
        return self.ox + cell[1] * self.tile + self.tile // 2, self.oy + cell[0] * self.tile + \
            self.tile // 2

    def rect(self, cell: Cell) -> pygame.Rect:
        return pygame.Rect(self.ox + cell[1] * self.tile, self.oy + cell[0] * self.tile,
                           self.tile, self.tile)

    def quad(self, cell: Cell) -> list[tuple[int, int]]:
        r = self.rect(cell)
        return [r.topleft, r.topright, r.bottomright, r.bottomleft]

    def cell_at(self, pos: tuple[int, int], maze: Maze) -> Cell | None:
        c, r = (pos[0] - self.ox) // self.tile, (pos[1] - self.oy) // self.tile
        return (r, c) if (r, c) in maze.floor else None


Grid = Geometry | render3d.Grid3D  # what overlays draw on: the 2D board or the projected 3D floor


def board_geometry(maze: Maze, area: pygame.Rect | None = None) -> Geometry:
    """Fit the maze into `area` (default: the 672x672 board at (0, 48), 32 px tiles at 21x21)."""
    area = area or pygame.Rect(C.BOARD_X, C.BOARD_Y, C.BOARD_PX, C.BOARD_PX)
    tile = min(area.w // maze.cols, area.h // maze.rows)
    return Geometry(tile, area.x + (area.w - tile * maze.cols) // 2,
                    area.y + (area.h - tile * maze.rows) // 2)


def draw_maze(surf: pygame.Surface, maze: Maze, g: Geometry) -> None:
    """Floor and walls (walls with a lighter top edge)."""
    edge = max(2, g.tile // 10)
    for r in range(maze.rows):
        for c in range(maze.cols):
            rect = g.rect((r, c))
            if (r, c) in maze.floor:
                pygame.draw.rect(surf, C.COLOR_FLOOR, rect)
            else:
                pygame.draw.rect(surf, C.COLOR_WALL, rect)
                pygame.draw.rect(surf, C.COLOR_WALL_EDGE, (rect.x, rect.y, rect.w, edge))


def shade_cells(surf: pygame.Surface, g: Grid, cells: Iterable[Cell], color: Color,
                alpha: int) -> None:
    """Translucent fill over each cell (a projected quad on the 3D board)."""
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for cell in cells:
        pygame.draw.polygon(layer, (*color, alpha), g.quad(cell))
    surf.blit(layer, (0, 0))


def draw_path(surf: pygame.Surface, g: Grid, path: list[Cell], color: Color = C.COLOR_PATH,
              dots: bool = True) -> None:
    """Planned path: a thin line through the cells plus a dot on each cell."""
    if len(path) > 1:
        pygame.draw.lines(surf, color, False, [g.center(c) for c in path], max(2, g.tile // 12))
    if dots:
        for c in path[1:]:
            pygame.draw.circle(surf, color, g.center(c), max(2, g.tile // 7))


def draw_board(surf: pygame.Surface, fonts: Fonts, state: GameState, exit_known: bool,
               g: Geometry | None = None, under: Callable[[Grid], None] | None = None) -> None:
    """Maze, features and all characters. No fog: everything on the board is drawn.

    `exit_known` = the viewer may see the exit (Tom only after the alarm; the
    exit is hidden from him until then, a rule, not fog). `under` draws overlays
    between floor and pieces.
    """
    maze = state.maze
    pygame.draw.rect(surf, C.COLOR_BG, (C.BOARD_X, C.BOARD_Y, C.BOARD_PX, C.BOARD_PX))
    r3d = render3d.get_renderer() if g is None else None
    if r3d is not None:  # 3D scene rendered offscreen; overlays are drawn on top, projected
        surf.blit(r3d.render(state, exit_known), (C.BOARD_X, C.BOARD_Y))
        if under is not None:
            under(r3d.grid)
        for name, pos in r3d.labels.items():
            rgb = tuple(int(255 * v) for v in render3d.ROLE_RGB[name])
            chip(surf, fonts.tiny, render3d.LABEL[name], (pos[0] - 26, pos[1] - 12), rgb)
        z = r3d.bruno_label_pos(state)
        if z is not None:
            text(surf, fonts.big, "z", z, C.COLOR_TEXT_DIM, center=True)
        return
    g = g or board_geometry(maze)
    draw_maze(surf, maze, g)
    if under is not None:
        under(g)
    draw_kennel(surf, g.center(maze.kennel), g.tile)
    if exit_known:
        draw_exit(surf, g.center(maze.exit), g.tile, state.exit_open)
    for t in state.traps:
        draw_trap(surf, g.center(t), g.tile)
    for k in state.keys:
        draw_key(surf, g.center(k), g.tile)
    b = state.bruno
    if b is not None:
        bx, by = g.center(b.pos)
        if b.pos in (state.tom, state.jerry):  # sharing a cell: nudge him so he stays visible
            bx, by = bx + g.tile // 4, by + g.tile // 4
        draw_bruno(surf, fonts, (bx, by), g.tile, b.state == SLEEP)
    draw_tom(surf, g.center(state.tom), g.tile, state.tom_stun)
    draw_jerry(surf, g.center(state.jerry), g.tile)


def draw_trap(surf: pygame.Surface, ctr: tuple[int, int], t: int) -> None:
    """Mouse trap: a red spring ring with a cross, drawn on the floor."""
    cx, cy = ctr
    r = t // 3
    pygame.draw.circle(surf, C.COLOR_TRAP, ctr, r, 3)
    pygame.draw.line(surf, C.COLOR_TRAP, (cx - r // 2, cy - r // 2), (cx + r // 2, cy + r // 2), 2)
    pygame.draw.line(surf, C.COLOR_TRAP, (cx - r // 2, cy + r // 2), (cx + r // 2, cy - r // 2), 2)


def draw_key(surf: pygame.Surface, ctr: tuple[int, int], t: int) -> None:
    cx, cy = ctr
    r = max(3, t // 6)
    pygame.draw.circle(surf, C.COLOR_CHEESE, (cx - t // 6, cy), r, max(2, r // 2))
    pygame.draw.rect(surf, C.COLOR_CHEESE, (cx - t // 6 + r, cy - 1, t // 3, max(2, t // 14)))
    pygame.draw.rect(surf, C.COLOR_CHEESE, (cx + t // 8, cy, max(2, t // 14), t // 8))


def draw_exit(surf: pygame.Surface, ctr: tuple[int, int], t: int, is_open: bool) -> None:
    cx, cy = ctr
    color = C.COLOR_EXIT_OPEN if is_open else C.COLOR_EXIT_LOCKED
    door = pygame.Rect(0, 0, int(t * 0.6), int(t * 0.8))
    door.center = ctr
    pygame.draw.rect(surf, color, door, border_radius=max(2, t // 8))
    pygame.draw.circle(surf, (20, 20, 20), (door.right - t // 7, cy), max(1, t // 16))
    if not is_open:
        body = pygame.Rect(0, 0, t // 3, t // 4)
        body.center = (cx, cy + t // 10)
        pygame.draw.arc(surf, (230, 230, 230), (cx - t // 9, cy - t // 6, 2 * t // 9, t // 4),
                        0, math.pi, max(1, t // 16))
        pygame.draw.rect(surf, (230, 230, 230), body)


def draw_kennel(surf: pygame.Surface, ctr: tuple[int, int], t: int) -> None:
    cx, cy = ctr
    base = pygame.Rect(cx - int(t * 0.4), cy - t // 10, int(t * 0.8), int(t * 0.45))
    pygame.draw.rect(surf, C.COLOR_KENNEL, base)
    roof = [(cx - int(t * 0.46), cy - t // 10), (cx, cy - int(t * 0.42)),
            (cx + int(t * 0.46), cy - t // 10)]
    pygame.draw.polygon(surf, (0x6D, 0x4C, 0x41), roof)
    pygame.draw.circle(surf, (40, 30, 26), (cx, base.bottom), t // 6, draw_top_left=True,
                       draw_top_right=True)


def draw_tom(surf: pygame.Surface, ctr: tuple[int, int], t: int, stun: int) -> None:
    """Orange circle with two triangle ears; stars above the head while stunned."""
    cx, cy = ctr
    r = int(t * 0.33)
    for s in (-1, 1):
        ear = [(cx + s * int(t * 0.34), cy - int(t * 0.08)), (cx + s * int(t * 0.3),
               cy - int(t * 0.46)), (cx + s * int(t * 0.06), cy - int(t * 0.28))]
        pygame.draw.polygon(surf, C.COLOR_TOM, ear)
    pygame.draw.circle(surf, C.COLOR_TOM, ctr, r)
    for s in (-1, 1):
        pygame.draw.circle(surf, (30, 30, 30), (cx + s * t // 8, cy - t // 14), max(1, t // 16))
        pygame.draw.line(surf, (60, 40, 20), (cx + s * t // 10, cy + t // 10),
                         (cx + s * int(t * 0.42), cy + t // 14), 1)
    if stun > 0:
        for i in range(3):
            draw_star(surf, (cx - t // 4 + i * t // 4, cy - int(t * 0.5)), max(2, t // 10))


def draw_star(surf: pygame.Surface, ctr: tuple[int, int], r: int) -> None:
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r / 2.2
        pts.append((ctr[0] + rad * math.cos(ang), ctr[1] + rad * math.sin(ang)))
    pygame.draw.polygon(surf, C.COLOR_STAR, pts)


def draw_jerry(surf: pygame.Surface, ctr: tuple[int, int], t: int) -> None:
    """Grey circle with two round ears and a tail line."""
    cx, cy = ctr
    pygame.draw.lines(surf, C.COLOR_JERRY, False, [(cx + t // 5, cy + t // 6),
                      (cx + int(t * 0.4), cy + int(t * 0.3)), (cx + int(t * 0.46), cy + t // 8)],
                      max(1, t // 16))
    for s in (-1, 1):
        ear = (cx + s * int(t * 0.22), cy - int(t * 0.24))
        pygame.draw.circle(surf, C.COLOR_JERRY, ear, int(t * 0.14))
        pygame.draw.circle(surf, C.COLOR_JERRY_EAR, ear, int(t * 0.08))
    pygame.draw.circle(surf, C.COLOR_JERRY, ctr, int(t * 0.27))
    for s in (-1, 1):
        pygame.draw.circle(surf, (20, 20, 20), (cx + s * t // 10, cy - t // 20), max(1, t // 18))
    pygame.draw.circle(surf, C.COLOR_JERRY_EAR, (cx, cy + t // 10), max(1, t // 16))


def draw_bruno(surf: pygame.Surface, fonts: Fonts, ctr: tuple[int, int], t: int,
               asleep: bool) -> None:
    """Brown rounded square with a spiked collar; 'z' while asleep."""
    cx, cy = ctr
    body = pygame.Rect(0, 0, int(t * 0.72), int(t * 0.66))
    body.center = (cx, cy + t // 16)
    pygame.draw.rect(surf, C.COLOR_BRUNO, body, border_radius=max(3, t // 5))
    collar_y = body.bottom - t // 6
    for i in range(4):
        pygame.draw.circle(surf, C.COLOR_SPIKE, (body.left + (i + 1) * body.w // 5, collar_y),
                           max(1, t // 16))
    if asleep:
        text(surf, fonts.normal, "z", (cx + t // 3, cy - t // 2), C.COLOR_TEXT, center=True)
    else:
        for s in (-1, 1):
            pygame.draw.circle(surf, (15, 15, 15), (cx + s * t // 8, cy - t // 12),
                               max(1, t // 14))


# ------------------------------------------------------------------ top bar and panel


def draw_top_bar(surf: pygame.Surface, fonts: Fonts, state: GameState, middle: str,
                 right: str) -> None:
    """Turn counter with progress bar, key icons, matchup / difficulty, role or speed."""
    w = surf.get_width()
    pygame.draw.rect(surf, C.COLOR_PANEL, (0, 0, w, C.TOP_BAR_H))
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (0, C.TOP_BAR_H - 1), (w, C.TOP_BAR_H - 1))
    turn = min(state.turn, C.TURN_LIMIT)
    label = text(surf, fonts.normal, f"Turn {turn}/{C.TURN_LIMIT}", (18, 12))
    bar = pygame.Rect(label.right + 14, 19, 150, 10)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, bar, border_radius=5)
    fill = bar.copy()
    fill.w = int(bar.w * turn / C.TURN_LIMIT)
    pygame.draw.rect(surf, C.COLOR_ACCENT, fill, border_radius=5)
    keys = text(surf, fonts.normal, "Keys", (bar.right + 30, 12), C.COLOR_TEXT_DIM)
    for i in range(C.NUM_KEYS):
        width = 0 if i < state.keys_taken else 2
        pygame.draw.circle(surf, C.COLOR_CHEESE, (keys.right + 18 + i * 24, 24), 9, width)
    text(surf, fonts.normal, middle, (keys.right + 110, 12), C.COLOR_TEXT_DIM)
    text(surf, fonts.normal, right, (w - 18, 12), C.COLOR_TEXT, right=True)


@dataclass
class AIView:
    """What the panel shows about one AI agent."""

    role: str
    difficulty: str
    mode: str
    algorithm: str
    nodes: int
    ms: float
    fuzzy: FuzzyResult | None
    belief: str


def fuzzy_bars(surf: pygame.Surface, fonts: Fonts, x: int, y: int, w: int,
               res: FuzzyResult, row_h: int = 18) -> int:
    """One bar per output set (membership at the centroid); the chosen set is bright."""
    names = list(res.output_memberships)
    label_w = 64
    for name in names:
        mu = res.output_memberships[name]
        color = MODE_COLORS.get(name, C.COLOR_ACCENT)
        text(surf, fonts.tiny, name if len(name) <= 7 else name[:7], (x, y + 2), C.COLOR_TEXT_DIM)
        bar = pygame.Rect(x + label_w, y + 3, w - label_w - 44, row_h - 7)
        pygame.draw.rect(surf, C.COLOR_PANEL_LINE, bar, border_radius=4)
        fill = bar.copy()
        fill.w = max(0, int(bar.w * mu))
        if fill.w:
            pygame.draw.rect(surf, color, fill, border_radius=4)
        text(surf, fonts.tiny, f"{mu:.2f}", (x + w, y + 2), C.COLOR_TEXT, right=True)
        y += row_h
    return y


def draw_ai_block(surf: pygame.Surface, fonts: Fonts, v: AIView, x: int, y: int, w: int,
                  compact: bool) -> int:
    """Header, mode chip, algorithm/nodes/ms, fuzzy bars, belief. Returns the next y."""
    font = fonts.normal if compact else fonts.big
    text(surf, font, f"AI {v.role.title()}  ({v.difficulty})", (x, y), ROLE_COLORS[v.role])
    y += 26 if compact else 34
    rect = chip(surf, fonts.small, v.mode, (x, y), MODE_COLORS.get(v.mode, C.COLOR_ACCENT))
    text(surf, fonts.small, f"{v.nodes} nodes   {v.ms:.1f} ms", (rect.right + 12, y + 5),
         C.COLOR_TEXT_DIM)
    y += rect.h + 6
    text(surf, fonts.small, fit(fonts.small, v.algorithm, w), (x, y))
    y += 20
    if v.fuzzy is not None:
        y = fuzzy_bars(surf, fonts, x, y + 2, w, v.fuzzy, 16 if compact else 18)
        text(surf, fonts.tiny, f"centroid {v.fuzzy.centroid:.1f}", (x, y), C.COLOR_TEXT_DIM)
        y += 16
    else:
        note = ("EASY: no fuzzy logic (greedy)" if v.difficulty == "EASY"
                else "fuzzy mode from the first move")
        text(surf, fonts.tiny, note, (x, y + 2), C.COLOR_TEXT_DIM)
        y += 18
    for part in v.belief.split(";"):  # "memory; Bruno state": one row each, never clipped
        text(surf, fonts.small, fit(fonts.small, part.strip(), w), (x, y))
        y += 20
    return y + 2


def section(surf: pygame.Surface, fonts: Fonts, title: str, lines: list[str], x: int,
            y: int, w: int) -> int:
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x, y), (x + w, y))
    text(surf, fonts.small, title, (x, y + 8), C.COLOR_ACCENT)
    y += 34
    for line in lines:
        text(surf, fonts.small, fit(fonts.small, line, w), (x, y))
        y += 22
    return y + 6


def draw_panel(surf: pygame.Surface, fonts: Fonts, ais: list[AIView], bruno: list[str],
               events: list[str], footer: list[str], legend: bool) -> None:
    """Right panel: one block per AI, Bruno, event log, legend / controls."""
    x0 = C.PANEL_X
    pygame.draw.rect(surf, C.COLOR_PANEL, (x0, C.TOP_BAR_H, C.PANEL_W, C.WINDOW_H - C.TOP_BAR_H))
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x0, C.TOP_BAR_H), (x0, C.WINDOW_H))
    x, y, w = x0 + 18, C.TOP_BAR_H + 12, C.PANEL_W - 36
    compact = len(ais) > 1
    for v in ais:
        y = draw_ai_block(surf, fonts, v, x, y, w, compact)
        if compact:
            y += 4
    y = section(surf, fonts, "Bruno", bruno, x, y, w)
    n_events = 4 if compact else C.EVENT_LOG_LINES
    section(surf, fonts, "Events", events[-n_events:] or ["-"], x, y, w)
    bottom = C.WINDOW_H - 8 - 17 * len(footer)
    if legend:
        draw_legend(surf, fonts, x, bottom - 70)
    for i, line in enumerate(footer):
        text(surf, fonts.tiny, line, (x, bottom + i * 17), C.COLOR_TEXT_DIM)


def draw_legend(surf: pygame.Surface, fonts: Fonts, x: int, y: int) -> None:
    """3x2 grid of icons with names."""
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x, y - 8), (C.WINDOW_W - 18, y - 8))
    t = 26
    icons: list[tuple[str, Callable[[tuple[int, int]], None]]] = [
        ("Jerry", lambda p: draw_jerry(surf, p, t)),
        ("Tom", lambda p: draw_tom(surf, p, t, 0)),
        ("Bruno", lambda p: draw_bruno(surf, fonts, p, t, False)),
        ("Key", lambda p: draw_key(surf, p, t)),
        ("Exit", lambda p: draw_exit(surf, p, t, False)),
        ("Kennel", lambda p: draw_kennel(surf, p, t)),
    ]
    for i, (name, draw) in enumerate(icons):
        cx, cy = x + 14 + (i % 3) * 128, y + 14 + (i // 3) * 30
        draw((cx, cy))
        text(surf, fonts.small, name, (cx + 22, cy - 7))


# ------------------------------------------------------------------ fuzzy view


def draw_curve_box(surf: pygame.Surface, fonts: Fonts, rect: pygame.Rect, title: str,
                   lo: float, hi: float, curves: list[tuple[str, Callable[[float], float], Color]],
                   marker: float | None, fill: list[tuple[int, float]] | None = None) -> None:
    """Membership curves of one variable on [lo, hi]; `marker` = crisp value line;
    `fill` = aggregated output shape (x, mu) drawn underneath."""
    pygame.draw.rect(surf, (238, 241, 247), rect, border_radius=6)
    text(surf, fonts.small, title, (rect.x + 8, rect.y + 4))
    plot = pygame.Rect(rect.x + 8, rect.y + 24, rect.w - 16, rect.h - 44)

    def px(x: float, mu: float) -> tuple[int, int]:
        return (int(plot.x + (x - lo) / (hi - lo) * plot.w), int(plot.bottom - mu * plot.h))

    pygame.draw.line(surf, C.COLOR_PANEL_LINE, plot.bottomleft, plot.bottomright)
    if fill:
        pts = [px(lo, 0)] + [px(x, mu) for x, mu in fill] + [px(hi, 0)]
        pygame.draw.polygon(surf, (190, 205, 228), pts)
    lx = rect.x + 8
    for name, mf, color in curves:
        n = 120
        pygame.draw.lines(surf, color, False,
                          [px(lo + (hi - lo) * i / n, mf(lo + (hi - lo) * i / n))
                           for i in range(n + 1)], 2)
        lab = text(surf, fonts.tiny, name, (lx, plot.bottom + 4), color)
        lx = lab.right + 10
    if marker is not None:
        mx = px(marker, 0)[0]
        pygame.draw.line(surf, (20, 24, 36), (mx, plot.y), (mx, plot.bottom), 2)
        text(surf, fonts.tiny, f"{marker:.2f}".rstrip("0").rstrip("."), (rect.right - 8,
             rect.y + 6), (20, 24, 36), right=True)


PALETTE = [(0x5D, 0xAD, 0xE2), (0xF5, 0xB0, 0x41), (0xE7, 0x4C, 0x3C), (0x58, 0xD6, 0x8D)]


def draw_fuzzy_view(surf: pygame.Surface, fonts: Fonts, rect: pygame.Rect, system: FuzzySystem,
                    inputs: dict[str, float], res: FuzzyResult,
                    selected: str | None = None) -> None:
    """Membership curves of every input (crisp value marked), rule strengths, the
    aggregated output with the centroid line, and the chosen mode."""
    pygame.draw.rect(surf, C.COLOR_PANEL, rect)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, rect, 1)
    text(surf, fonts.big, f"Fuzzy controller: {system.role.title()}", (rect.x + 14, rect.y + 10))
    names = list(system.inputs)
    col_w = (rect.w - 14 * (len(names) + 1)) // len(names)
    for i, name in enumerate(names):
        var = system.inputs[name]
        box = pygame.Rect(rect.x + 14 + i * (col_w + 14), rect.y + 48, col_w, 150)
        curves = [(s, mf, PALETTE[j % len(PALETTE)]) for j, (s, mf) in enumerate(var.sets.items())]
        draw_curve_box(surf, fonts, box, name, var.lo, var.hi, curves, inputs[name])
        if name == selected:
            pygame.draw.rect(surf, C.COLOR_CHEESE, box, 2, border_radius=6)
    out = system.output
    box = pygame.Rect(rect.x + 14, rect.y + 212, rect.w - 28, 170)
    curves = [(s, mf, MODE_COLORS.get(s, C.COLOR_ACCENT)) for s, mf in out.sets.items()]
    draw_curve_box(surf, fonts, box, f"{out.name}: clipped rules, max-aggregated", out.lo, out.hi,
                   curves, res.centroid, res.aggregated)
    y = box.bottom + 12
    text(surf, fonts.normal, "Rules (strength = min of antecedents)", (rect.x + 14, y))
    y += 26
    for rid, ante, out_set in system.rules:
        st = res.rule_strengths[rid]
        bar = pygame.Rect(rect.x + 14, y + 3, 90, 12)
        pygame.draw.rect(surf, C.COLOR_PANEL_LINE, bar, border_radius=3)
        if st > 0:
            pygame.draw.rect(surf, MODE_COLORS.get(out_set, C.COLOR_ACCENT),
                             (bar.x, bar.y, max(2, int(bar.w * st)), bar.h), border_radius=3)
        color = C.COLOR_TEXT if st > 0 else C.COLOR_TEXT_DIM
        text(surf, fonts.small, f"{st:.2f}  {rid}: {system.rule_text((rid, ante, out_set))}",
             (bar.right + 10, y), color)
        y += 20
    y += 8
    text(surf, fonts.normal, f"Centroid {res.centroid:.1f}  ->  mode", (rect.x + 14, y + 4))
    chip(surf, fonts.normal, res.mode, (rect.x + 250, y), MODE_COLORS.get(res.mode, C.COLOR_ACCENT))


# ------------------------------------------------------------------ menu, help, end


def draw_menu(surf: pygame.Surface, fonts: Fonts, actions: list[str], options: list[str],
              selected: int, hint: str) -> list[pygame.Rect]:
    """Title, action buttons (left column) and options (right column, Left/Right to
    change). `selected` indexes actions + options. Returns all rects for mouse hits."""
    surf.fill(C.COLOR_BG)
    text(surf, fonts.title, C.TITLE, (C.WINDOW_W // 2, 80), C.COLOR_CHEESE, center=True)
    draw_jerry(surf, (C.WINDOW_W // 2 - 70, 160), 64)
    draw_key(surf, (C.WINDOW_W // 2, 160), 64)
    draw_tom(surf, (C.WINDOW_W // 2 + 70, 160), 64, 0)
    rects = []
    text(surf, fonts.small, "Play", (C.WINDOW_W // 2 - 340, 214), C.COLOR_TEXT_DIM)
    text(surf, fonts.small, "Options (Left / Right to change)", (C.WINDOW_W // 2 + 30, 214),
         C.COLOR_TEXT_DIM)
    for col, items in enumerate((actions, options)):
        for i, item in enumerate(items):
            idx = len(rects)
            rect = pygame.Rect(0, 0, 320, 44)
            rect.topleft = (C.WINDOW_W // 2 - 340 + col * 370, 240 + i * 56)
            sel = idx == selected
            pygame.draw.rect(surf, C.COLOR_ACCENT if sel else C.COLOR_PANEL, rect, border_radius=10)
            if col == 1:
                text(surf, fonts.normal, "<", (rect.x + 16, rect.centery), DARK_TEXT if sel
                     else C.COLOR_TEXT_DIM, center=True)
                text(surf, fonts.normal, ">", (rect.right - 16, rect.centery), DARK_TEXT if sel
                     else C.COLOR_TEXT_DIM, center=True)
            text(surf, fonts.normal, item, rect.center, DARK_TEXT if sel else C.COLOR_TEXT,
                 center=True)
            rects.append(rect)
    text(surf, fonts.small, hint, (C.WINDOW_W // 2, C.WINDOW_H - 34), C.COLOR_TEXT_DIM,
         center=True)
    return rects


HELP_STEPS = [
    "1. Jerry (grey mouse) must collect all 3 golden keys.",
    "2. The 3rd key opens the exit (red door turns green) and alerts Tom where it is.",
    "3. Walk onto the open exit to win. Tom wins if he catches Jerry or turn 120 passes.",
    "4. Both see only 5 steps along corridors. Tom smells the keys, not Jerry.",
    "5. Step on the kennel to wake Bruno (twice per game): he guards Jerry and bites Tom.",
    "6. From turn 60 Tom sniffs you out every 10 turns. Stay moving, or be found.",
]
HELP_KEYS = [
    "WASD / arrows move, Space wait, Q set a mouse trap, E whistle Bruno back, P pause, Esc menu.",
    "Human games hide the AI's plans and fuzzy inputs. Watch AI vs AI for Tab path,",
    "E explored cells, F fuzzy panel, N single step, + / - speed, T save AI traces.",
]


def draw_help(surf: pygame.Surface, fonts: Fonts) -> None:
    """How to Play overlay: 5 short steps plus the controls."""
    shade = pygame.Surface((C.WINDOW_W, C.WINDOW_H), pygame.SRCALPHA)
    shade.fill((30, 36, 50, 150))
    surf.blit(shade, (0, 0))
    box = pygame.Rect(0, 0, 860, 470)
    box.center = (C.WINDOW_W // 2, C.WINDOW_H // 2)
    pygame.draw.rect(surf, C.COLOR_PANEL, box, border_radius=16)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, box, 2, border_radius=16)
    text(surf, fonts.big, "How to Play", (box.centerx, box.y + 36), C.COLOR_CHEESE, center=True)
    for i, line in enumerate(HELP_STEPS):
        text(surf, fonts.normal, line, (box.x + 40, box.y + 80 + i * 40))
    for i, line in enumerate(HELP_KEYS):
        text(surf, fonts.small, line, (box.x + 40, box.y + 342 + i * 24), C.COLOR_TEXT_DIM)
    text(surf, fonts.small, "Press any key to close", (box.centerx, box.bottom - 30),
         C.COLOR_TEXT_DIM, center=True)


def draw_end(surf: pygame.Surface, fonts: Fonts, winner: str, reason: str,
             stats: list[str], buttons: list[str]) -> list[pygame.Rect]:
    """Overlay box with winner, reason, stats and buttons; returns button rects."""
    shade = pygame.Surface((C.WINDOW_W, C.WINDOW_H), pygame.SRCALPHA)
    shade.fill((30, 36, 50, 120))
    surf.blit(shade, (0, 0))
    box = pygame.Rect(0, 0, 600, 430)
    box.center = (C.WINDOW_W // 2, C.WINDOW_H // 2)
    pygame.draw.rect(surf, C.COLOR_PANEL, box, border_radius=16)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, box, 2, border_radius=16)
    color = ROLE_COLORS.get(winner, C.COLOR_TEXT)
    text(surf, fonts.title, f"{winner.title()} wins!", (box.centerx, box.top + 56), color,
         center=True)
    text(surf, fonts.normal, reason, (box.centerx, box.top + 104), C.COLOR_TEXT_DIM, center=True)
    for i, line in enumerate(stats):
        text(surf, fonts.normal, line, (box.left + 50, box.top + 138 + i * 28))
    rects = []
    for i, label in enumerate(buttons):
        rect = pygame.Rect(0, 0, 170, 44)
        rect.center = (box.left + 105 + i * 195, box.bottom - 44)
        pygame.draw.rect(surf, C.COLOR_ACCENT, rect, border_radius=10)
        text(surf, fonts.small, label, rect.center, DARK_TEXT, center=True)
        rects.append(rect)
    return rects
