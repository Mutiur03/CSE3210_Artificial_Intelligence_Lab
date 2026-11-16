"""Pygame drawing: board, characters, fog, top bar, right panel, menu, end screen.

Pure drawing. No game rules here; everything shown comes from GameState,
Observation or Decision objects passed in by main.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pygame

import config as C
from game import JERRY, SLEEP, TOM, GameState, Observation
from maze import Maze

Color = tuple[int, int, int]


@dataclass
class Fonts:
    """Default pygame font in a few sizes (no font files needed)."""

    small: pygame.font.Font = field(default_factory=lambda: pygame.font.Font(None, 20))
    normal: pygame.font.Font = field(default_factory=lambda: pygame.font.Font(None, 24))
    big: pygame.font.Font = field(default_factory=lambda: pygame.font.Font(None, 36))
    title: pygame.font.Font = field(default_factory=lambda: pygame.font.Font(None, 72))


@dataclass
class PanelInfo:
    """Text content for the right panel."""

    role: str
    mode: str
    algorithm: str
    nodes: int
    ms: float
    belief: str
    bruno: list[str]
    events: list[str]


def text(surf: pygame.Surface, font: pygame.font.Font, s: str, pos: tuple[int, int],
         color: Color = C.COLOR_TEXT, center: bool = False) -> pygame.Rect:
    img = font.render(s, True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surf.blit(img, rect)
    return rect


# ------------------------------------------------------------------ board


def board_geometry(maze: Maze) -> tuple[int, int, int]:
    """(tile size, x offset, y offset). 21x21 gives 32 px tiles at (0, 48)."""
    tile = C.BOARD_PX // max(maze.rows, maze.cols)
    ox = C.BOARD_X + (C.BOARD_PX - tile * maze.cols) // 2
    oy = C.BOARD_Y + (C.BOARD_PX - tile * maze.rows) // 2
    return tile, ox, oy


def draw_board(surf: pygame.Surface, fonts: Fonts, state: GameState,
               viewer: Observation | None) -> None:
    """Maze, features, fog and characters. `viewer` = human's observation (None = no fog)."""
    maze = state.maze
    tile, ox, oy = board_geometry(maze)
    pygame.draw.rect(surf, C.COLOR_BG, (C.BOARD_X, C.BOARD_Y, C.BOARD_PX, C.BOARD_PX))
    fog = pygame.Surface((tile, tile), pygame.SRCALPHA)
    fog.fill((0, 0, 0, C.FOG_ALPHA))
    edge = max(2, tile // 10)
    for r in range(maze.rows):
        for c in range(maze.cols):
            x, y = ox + c * tile, oy + r * tile
            if (r, c) in maze.floor:
                pygame.draw.rect(surf, C.COLOR_FLOOR, (x, y, tile, tile))
            else:
                pygame.draw.rect(surf, C.COLOR_WALL, (x, y, tile, tile))
                pygame.draw.rect(surf, C.COLOR_WALL_EDGE, (x, y, tile, edge))
            if viewer is not None and (r, c) not in viewer.visible_cells:
                surf.blit(fog, (x, y))

    def center(cell: tuple[int, int]) -> tuple[int, int]:
        return ox + cell[1] * tile + tile // 2, oy + cell[0] * tile + tile // 2

    draw_kennel(surf, center(maze.kennel), tile)
    if viewer is None or viewer.exit_cell is not None:
        draw_exit(surf, center(maze.exit), tile, state.exit_open)
    for k in state.keys:
        draw_key(surf, center(k), tile)
    sees = viewer.visible_cells if viewer is not None else None
    b = state.bruno
    if b is not None and (sees is None or b.pos in sees):
        draw_bruno(surf, fonts, center(b.pos), tile, b.state == SLEEP)
    if sees is None or state.tom in sees:
        draw_tom(surf, center(state.tom), tile, state.tom_stun)
    if sees is None or state.jerry in sees:
        draw_jerry(surf, center(state.jerry), tile)


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


# ------------------------------------------------------------------ bars and panel


def draw_top_bar(surf: pygame.Surface, fonts: Fonts, state: GameState, role: str,
                 opponent: str) -> None:
    """Turn counter with progress bar, key icons, opponent difficulty, human role."""
    pygame.draw.rect(surf, C.COLOR_PANEL, (0, 0, C.WINDOW_W, C.TOP_BAR_H))
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (0, C.TOP_BAR_H - 1), (C.WINDOW_W, C.TOP_BAR_H - 1))
    turn = min(state.turn, C.TURN_LIMIT)
    text(surf, fonts.normal, f"Turn {turn}/{C.TURN_LIMIT}", (14, 15))
    bar = pygame.Rect(130, 18, 200, 12)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, bar, border_radius=6)
    fill = bar.copy()
    fill.w = int(bar.w * turn / C.TURN_LIMIT)
    pygame.draw.rect(surf, C.COLOR_ACCENT, fill, border_radius=6)
    text(surf, fonts.normal, "Keys", (360, 15))
    for i in range(C.NUM_KEYS):
        center = (420 + i * 26, 24)
        width = 0 if i < state.keys_taken else 2
        pygame.draw.circle(surf, C.COLOR_CHEESE, center, 9, width)
    text(surf, fonts.normal, opponent, (520, 15), C.COLOR_TEXT_DIM)
    text(surf, fonts.normal, f"You: {role}", (C.PANEL_X + 20, 15))


def draw_panel(surf: pygame.Surface, fonts: Fonts, info: PanelInfo) -> None:
    """Right panel: AI decision info, belief, Bruno, event log, legend."""
    x0 = C.PANEL_X
    pygame.draw.rect(surf, C.COLOR_PANEL, (x0, C.TOP_BAR_H, C.PANEL_W, C.WINDOW_H - C.TOP_BAR_H))
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x0, C.TOP_BAR_H), (x0, C.WINDOW_H))
    x, y = x0 + 20, C.TOP_BAR_H + 16
    text(surf, fonts.big, f"AI: {info.role}", (x, y))
    y += 40
    chip = text(surf, fonts.normal, info.mode, (x + 10, y + 5), (15, 18, 25))
    pygame.draw.rect(surf, C.COLOR_ACCENT, chip.inflate(20, 10), border_radius=12)
    text(surf, fonts.normal, info.mode, (x + 10, y + 5), (15, 18, 25))
    y += 38
    for label, val in (("Algorithm", info.algorithm), ("Nodes", str(info.nodes)),
                       ("Time", f"{info.ms:.2f} ms")):
        text(surf, fonts.small, label, (x, y), C.COLOR_TEXT_DIM)
        text(surf, fonts.normal, val, (x + 100, y - 2))
        y += 24
    y = section(surf, fonts, "Belief", [info.belief], x, y + 8)
    y = section(surf, fonts, "Bruno", info.bruno, x, y)
    y = section(surf, fonts, "Events", info.events[-C.EVENT_LOG_LINES:] or ["-"], x, y)
    draw_legend(surf, fonts, x, C.WINDOW_H - 92)


def section(surf: pygame.Surface, fonts: Fonts, title: str, lines: list[str], x: int,
            y: int) -> int:
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x, y), (C.WINDOW_W - 20, y))
    text(surf, fonts.small, title.upper(), (x, y + 8), C.COLOR_TEXT_DIM)
    y += 30
    for line in lines:
        text(surf, fonts.small, line, (x, y))
        y += 20
    return y + 8


def draw_legend(surf: pygame.Surface, fonts: Fonts, x: int, y: int) -> None:
    """3x2 grid of icons with names, plus the control hint."""
    pygame.draw.line(surf, C.COLOR_PANEL_LINE, (x, y - 8), (C.WINDOW_W - 20, y - 8))
    t = 28
    icons = [
        ("Jerry", lambda p: draw_jerry(surf, p, t)),
        ("Tom", lambda p: draw_tom(surf, p, t, 0)),
        ("Bruno", lambda p: draw_bruno(surf, fonts, p, t, False)),
        ("Key", lambda p: draw_key(surf, p, t)),
        ("Exit", lambda p: draw_exit(surf, p, t, False)),
        ("Kennel", lambda p: draw_kennel(surf, p, t)),
    ]
    for i, (name, draw) in enumerate(icons):
        cx, cy = x + 14 + (i % 3) * 130, y + 14 + (i // 3) * 32
        draw((cx, cy))
        text(surf, fonts.small, name, (cx + 22, cy - 7))
    text(surf, fonts.small, "WASD/arrows move, Space wait, Esc menu", (x, C.WINDOW_H - 20),
         C.COLOR_TEXT_DIM)


# ------------------------------------------------------------------ menu and end


def draw_menu(surf: pygame.Surface, fonts: Fonts, items: list[str], selected: int,
              hint: str) -> list[pygame.Rect]:
    """Title, menu items (selected highlighted), returns item rects for mouse hits."""
    surf.fill(C.COLOR_BG)
    text(surf, fonts.title, C.TITLE, (C.WINDOW_W // 2, 120), C.COLOR_CHEESE, center=True)
    draw_jerry(surf, (C.WINDOW_W // 2 - 60, 200), 64)
    draw_key(surf, (C.WINDOW_W // 2, 200), 64)
    draw_tom(surf, (C.WINDOW_W // 2 + 60, 200), 64, 0)
    rects = []
    for i, item in enumerate(items):
        rect = pygame.Rect(0, 0, 360, 44)
        rect.center = (C.WINDOW_W // 2, 290 + i * 56)
        sel = i == selected
        pygame.draw.rect(surf, C.COLOR_ACCENT if sel else C.COLOR_PANEL, rect, border_radius=10)
        text(surf, fonts.normal, item, rect.center, (15, 18, 25) if sel else C.COLOR_TEXT,
             center=True)
        rects.append(rect)
    text(surf, fonts.small, hint, (C.WINDOW_W // 2, C.WINDOW_H - 40), C.COLOR_TEXT_DIM,
         center=True)
    return rects


def draw_end(surf: pygame.Surface, fonts: Fonts, winner: str, reason: str,
             stats: list[str], buttons: list[str]) -> list[pygame.Rect]:
    """Overlay box with winner, reason, stats and buttons; returns button rects."""
    shade = pygame.Surface((C.WINDOW_W, C.WINDOW_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 150))
    surf.blit(shade, (0, 0))
    box = pygame.Rect(0, 0, 560, 420)
    box.center = (C.WINDOW_W // 2, C.WINDOW_H // 2)
    pygame.draw.rect(surf, C.COLOR_PANEL, box, border_radius=16)
    pygame.draw.rect(surf, C.COLOR_PANEL_LINE, box, 2, border_radius=16)
    color = C.COLOR_JERRY if winner == JERRY else C.COLOR_TOM if winner == TOM else C.COLOR_TEXT
    text(surf, fonts.title, f"{winner.title()} wins!", (box.centerx, box.top + 56), color,
         center=True)
    text(surf, fonts.normal, reason, (box.centerx, box.top + 104), C.COLOR_TEXT_DIM, center=True)
    for i, line in enumerate(stats):
        text(surf, fonts.normal, line, (box.left + 60, box.top + 140 + i * 28))
    rects = []
    for i, label in enumerate(buttons):
        rect = pygame.Rect(0, 0, 160, 44)
        rect.center = (box.left + 95 + i * 185, box.bottom - 44)
        pygame.draw.rect(surf, C.COLOR_ACCENT, rect, border_radius=10)
        text(surf, fonts.small, label, rect.center, (15, 18, 25), center=True)
        rects.append(rect)
    return rects
