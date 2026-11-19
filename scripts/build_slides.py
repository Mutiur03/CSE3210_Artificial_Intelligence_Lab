"""Build slides/cheese_heist.pptx (python-pptx, 16:9, dark theme) from the repo's real data.

Numbers come from results/experiments.json, results/demo_seeds.json, docs/scenario/*.md and
config.py; images are docs/scenario/*.png, docs/screens/*.png and results/E*.png.

Usage: python scripts/build_slides.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content as K  # noqa: E402

C = K.C
OUT = K.ROOT / "slides" / "cheese_heist.pptx"

BG, PANEL, LINE = RGBColor(0x10, 0x15, 0x1F), RGBColor(0x18, 0x1E, 0x2C), RGBColor(0x3A, 0x45, 0x5C)
TEXT, DIM = RGBColor(0xE2, 0xE6, 0xF0), RGBColor(0x8C, 0x96, 0xAA)
GOLD, BLUE, GREEN, ORANGE, RED = (
    RGBColor(0xFF, 0xD2, 0x3F),
    RGBColor(0x4F, 0xA3, 0xF7),
    RGBColor(0x2E, 0xCC, 0x71),
    RGBColor(0xF3, 0x8B, 0x2A),
    RGBColor(0xC0, 0x39, 0x2B),
)
FONT = "Segoe UI"
MONO = "Consolas"
W, H = 13.333, 7.5


class Deck:
    """Thin helper around python-pptx: dark slides, titles, bullets, tables, pictures."""

    def __init__(self) -> None:
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.n = 0
        self.images: list[Path] = []

    def slide(self, title: str, notes: str = "", subtitle: str = ""):  # type: ignore[no-untyped-def]
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.n += 1
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = BG
        if title:
            self.text(s, title, 0.55, 0.32, W - 1.1, 0.7, size=28, bold=True, color=TEXT)
            bar = s.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.0), Inches(0.9), Inches(0.06)
            )
            bar.fill.solid()
            bar.fill.fore_color.rgb = GOLD
            bar.line.fill.background()
        if subtitle:
            self.text(s, subtitle, 0.55, 1.1, W - 1.1, 0.4, size=14, color=DIM)
        self.text(
            s,
            f"Cheese Heist  |  {self.n}",
            W - 3.0,
            H - 0.4,
            2.5,
            0.3,
            size=10,
            color=DIM,
            align=PP_ALIGN.RIGHT,
        )
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def text(
        self,
        s,
        text,
        x,
        y,
        w,
        h,
        size=16,
        bold=False,
        color=TEXT,
        font=FONT,  # type: ignore[no-untyped-def]
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    ):
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        for i, line in enumerate(text.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = line
            r.font.size, r.font.bold, r.font.name = Pt(size), bold, font
            r.font.color.rgb = color
        return tb

    def bullets(self, s, items, x, y, w, h, size=16, color=TEXT):  # type: ignore[no-untyped-def]
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(6)
            r0 = p.add_run()
            r0.text = "■  "
            r0.font.size, r0.font.color.rgb, r0.font.name = Pt(size - 6), GOLD, FONT
            r = p.add_run()
            r.text = item
            r.font.size, r.font.name = Pt(size), FONT
            r.font.color.rgb = color
        return tb

    def box(
        self,
        s,
        x,
        y,
        w,
        h,
        fill=PANEL,
        line=LINE,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
        text="",  # type: ignore[no-untyped-def]
        size=14,
        color=TEXT,
        bold=False,
    ):
        b = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        b.fill.solid()
        b.fill.fore_color.rgb = fill
        b.line.color.rgb = line
        b.line.width = Pt(1.25)
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            b.adjustments[0] = 0.12
        tf = b.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for i, line_ in enumerate(text.split("\n") if text else []):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = line_
            r.font.size, r.font.name, r.font.bold = Pt(size), FONT, bold
            r.font.color.rgb = color
        return b

    def arrow(self, s, x1, y1, x2, y2, color=BLUE, label="", lx=0.0, ly=0.0, lw=2.2):  # type: ignore[no-untyped-def]
        c = s.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
        )
        c.line.color.rgb = color
        c.line.width = Pt(2)
        ln = c.line._get_or_add_ln()
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)
        if label:
            self.text(
                s,
                label,
                (x1 + x2) / 2 + lx - lw / 2,
                (y1 + y2) / 2 + ly - 0.2,
                lw,
                0.5,
                size=11,
                color=DIM,
                align=PP_ALIGN.CENTER,
            )

    def picture(self, s, path: Path, x, y, w, h, backdrop=True):  # type: ignore[no-untyped-def]
        """Fit the image inside the (x, y, w, h) box, centred, keeping its aspect ratio."""
        iw, ih = Image.open(path).size
        scale = min(w / iw, h / ih)
        pw, ph = iw * scale, ih * scale
        px, py = x + (w - pw) / 2, y + (h - ph) / 2
        if backdrop:
            self.box(
                s,
                px - 0.06,
                py - 0.06,
                pw + 0.12,
                ph + 0.12,
                fill=RGBColor(0xFF, 0xFF, 0xFF),
                line=LINE,
                shape=MSO_SHAPE.RECTANGLE,
            )
        s.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))
        self.images.append(path)

    def table(
        self,
        s,
        rows,
        x,
        y,
        w,
        col_w=None,
        size=11,
        row_h=0.32,
        bold_first_col=False,  # type: ignore[no-untyped-def]
        align_right_from=1,
    ):
        nr, nc = len(rows), len(rows[0])
        gf = s.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
        tbl = gf.table
        tbl.first_row = True
        total = sum(col_w) if col_w else nc
        for j in range(nc):
            tbl.columns[j].width = Emu(int(Inches(w) * ((col_w[j] if col_w else 1) / total)))
        for i, row in enumerate(rows):
            tbl.rows[i].height = Inches(row_h)
            for j, val in enumerate(row):
                cell = tbl.cell(i, j)
                cell.fill.solid()
                cell.fill.fore_color.rgb = LINE if i == 0 else (PANEL if i % 2 else BG)
                cell.margin_left = cell.margin_right = Inches(0.06)
                cell.margin_top = cell.margin_bottom = Inches(0.02)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = cell.text_frame.paragraphs[0]
                p.alignment = (
                    PP_ALIGN.RIGHT
                    if (j >= align_right_from and i > 0 and _numeric(val))
                    else PP_ALIGN.LEFT
                )
                r = p.add_run()
                r.text = val.replace("**", "").replace("`", "")
                r.font.size, r.font.name = Pt(size), FONT
                r.font.bold = i == 0 or (bold_first_col and j == 0)
                r.font.color.rgb = GOLD if i == 0 else TEXT
        return gf

    def code(self, s, text, x, y, w, h, size=11):  # type: ignore[no-untyped-def]
        b = self.box(s, x, y, w, h, fill=RGBColor(0x0B, 0x0F, 0x17), shape=MSO_SHAPE.RECTANGLE)
        tf = b.text_frame
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = Inches(0.12)
        tf.margin_top = Inches(0.08)
        for i, line in enumerate(text.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = line
            r.font.size, r.font.name = Pt(size), MONO
            r.font.color.rgb = RGBColor(0xB8, 0xE0, 0xC0)
        return b


def _numeric(v: str) -> bool:
    return bool(re.fullmatch(r"[-+]?[\d.,]+%?", v))


def first_sentence(text: str) -> str:
    """First sentence of an experiment conclusion (not split on decimal points)."""
    m = re.search(r"(?<=[a-z%\)\d])\. (?=[A-Z])", text)
    return text[: m.start() + 1] if m else text


# ------------------------------------------------------------------ the deck


def build() -> Deck:  # noqa: PLR0915
    d = Deck()
    exp = K.experiments()
    sc = K.scenario_facts()
    seeds = K.demo_seeds()
    concl = K.results_conclusions()
    games = exp["E1"]["games"]

    # 1 title
    s = d.slide("")
    d.text(s, "Cheese Heist", 0.8, 2.1, 11.5, 1.2, size=60, bold=True, color=GOLD)
    d.text(
        s,
        "A turn-based cat-and-mouse maze game that plays with eight AI techniques",
        0.8,
        3.35,
        11.5,
        0.7,
        size=24,
    )
    d.text(
        s,
        "DFS  |  depth-limited search  |  bidirectional search  |  greedy best-first  |  A*  |  "
        "minimax with alpha-beta  |  MCTS  |  fuzzy logic",
        0.8,
        4.25,
        11.8,
        0.9,
        size=15,
        color=BLUE,
    )
    d.text(
        s,
        "Artificial Intelligence lab, final project  |  Pygame, no assets, no server",
        0.8,
        6.3,
        11,
        0.4,
        size=13,
        color=DIM,
    )

    # 2 overview
    s = d.slide(
        "Game overview", "Spectator view, HARD vs HARD. Tom orange tint = Tom's vision, Jerry blue."
    )
    d.bullets(
        s,
        [
            "Jerry (mouse) collects 3 keys, then runs to the exit",
            "Tom (cat) hunts her; Bruno (dog) is Jerry's bodyguard",
            f"{C.DEFAULT_SIZE}x{C.DEFAULT_SIZE} maze, generated from a seed (DFS + loops)",
            f"Fog of war: both sides see only {C.VISION_RADIUS} steps",
            "Human plays either role, or watch AI vs AI",
            f"Tom wins by capture or after {C.TURN_LIMIT} turns",
        ],
        0.55,
        1.4,
        5.0,
        5.0,
        size=18,
    )
    d.picture(s, K.SCREENS / "spectator.png", 5.7, 1.3, 7.1, 5.5)

    # 3 rules
    s = d.slide("Rules", "All numbers are constants in config.py.")
    d.bullets(
        s,
        [
            "Round: Jerry moves, Tom moves (unless stunned), Bruno steps, timers tick",
            "Actions: UP, DOWN, LEFT, RIGHT, WAIT; 1 cell; walls block; Tom is not faster",
            f"{C.NUM_KEYS} keys; the exit opens on the 3rd key and the ALARM tells Tom where it is",
            "Same cell after any move = capture (Tom wins)",
            f"Fairness: best start -> 3 keys -> exit walk <= {C.MAX_KEY_TOUR} steps (validated by bidirectional BFS)",
            f"Start distance >= {C.MIN_START_DISTANCE}, keys >= {C.MIN_KEY_SEPARATION} apart",
            "Same seed + config + actions = same game",
        ],
        0.55,
        1.4,
        12.2,
        5.4,
        size=20,
    )

    # 4 mechanics
    s = d.slide("Mechanics: fog of war and observations")
    d.bullets(
        s,
        [
            f"Vision = BFS path distance <= {C.VISION_RADIUS}; walls block sight",
            "Agents receive only an Observation, never the GameState",
            "Tom smells the keys; learns the exit only at the ALARM",
            "Agents remember where and when they last saw the opponent (age)",
            "Test: Tom's observation never holds Jerry beyond distance 5",
        ],
        0.55,
        1.4,
        5.2,
        5.0,
        size=18,
    )
    d.picture(s, K.SCREENS / "fog_view.png", 5.9, 1.3, 6.9, 5.5)

    # 5 Bruno FSM
    s = d.slide(
        "Mechanics: Bruno's finite-state machine",
        "Scripted FSM, BFS step per round; never harms Jerry.",
    )
    bx = {"SLEEP": (0.7, 1.7), "GUARD": (4.6, 1.7), "CHASE_CAT": (4.6, 4.7), "TIRED": (0.7, 4.7)}
    col = {"SLEEP": BLUE, "GUARD": GREEN, "CHASE_CAT": ORANGE, "TIRED": DIM}
    for name, (x, y) in bx.items():
        d.box(s, x, y, 2.3, 0.9, fill=PANEL, line=col[name], text=name, size=18, bold=True)
    d.arrow(
        s,
        3.0,
        2.15,
        4.6,
        2.15,
        GREEN,
        f"Jerry on kennel\n(activations < {C.BRUNO_MAX_ACTIVATIONS})",
        ly=-0.55,
        lw=2.4,
    )
    d.arrow(
        s,
        5.5,
        2.6,
        5.5,
        4.7,
        ORANGE,
        f"Tom within {C.BRUNO_CHASE_TRIGGER_DIST}",
        lx=-0.8,
        ly=0.5,
        lw=1.5,
    )
    d.arrow(
        s,
        6.0,
        4.7,
        6.0,
        2.6,
        GREEN,
        f"bite (stun {C.BRUNO_BITE_STUN})\nor Tom > {C.BRUNO_CHASE_GIVEUP_DIST}",
        lx=0.95,
        lw=1.6,
    )
    d.arrow(s, 4.6, 5.15, 3.0, 5.15, DIM, f"timer 0 ({C.BRUNO_GUARD_TURNS} rounds)", ly=0.3, lw=2.4)
    d.arrow(
        s,
        1.85,
        4.7,
        1.85,
        2.6,
        BLUE,
        f"at kennel,\ntired timer 0 ({C.BRUNO_TIRED_TURNS})",
        lx=-1.0,
        lw=1.6,
    )
    d.arrow(
        s,
        4.6,
        2.5,
        3.0,
        4.75,
        DIM,
        f"guard timer {C.BRUNO_GUARD_TURNS} -> 0",
        lx=-1.2, ly=0.2,
        lw=1.7,
    )
    d.bullets(
        s,
        [
            f"Bite: Tom skips {C.BRUNO_BITE_STUN} actions, bite cooldown {C.BRUNO_BITE_COOLDOWN}",
            "GUARD: follow Jerry if farther than 2",
            "TIRED walks home (no teleport), then SLEEP",
        ],
        0.7,
        6.0,
        7.5,
        1.4,
        size=14,
    )
    d.picture(s, K.SCEN / "bruno" / "strip.png", 8.6, 1.2, 4.4, 5.7)

    # 6 architecture
    s = d.slide(
        "System architecture", "Engine modules never import pygame; only ui, demo, main, record do."
    )
    d.text(s, "Engine (pure Python, headless)", 0.55, 1.25, 7.5, 0.4, size=14, color=DIM)
    eng = [
        ("maze.py", "DFS carve, validation"),
        ("game.py", "rules, fog, Bruno FSM"),
        ("search.py", "A*, greedy, DFS, DLS,\nbidirectional, IDDFS"),
        ("fuzzy.py", "Mamdani engine\n+ 2 controllers"),
        ("minimax.py", "alpha-beta"),
        ("mcts.py", "information-set UCT"),
    ]
    for i, (n, sub) in enumerate(eng):
        d.box(
            s,
            0.55 + (i % 3) * 2.55,
            1.7 + (i // 3) * 1.35,
            2.35,
            1.15,
            fill=PANEL,
            line=BLUE,
            text=f"{n}\n{sub}",
            size=12,
        )
    d.box(
        s,
        0.55,
        4.5,
        7.45,
        0.95,
        fill=PANEL,
        line=GOLD,
        text="agents.py: Decision, TomAgent, JerryAgent, difficulties\n"
        "reads Observation only; picks mode (fuzzy) -> algorithm",
        size=13,
    )
    d.text(s, "Presentation (Pygame)", 8.6, 1.25, 4.5, 0.4, size=14, color=DIM)
    for i, (n, sub) in enumerate(
        [
            ("main.py", "menu, game loop, input"),
            ("ui.py", "board, panel, overlays"),
            ("demo.py", "algorithm demo (F2)"),
            ("record.py", "headless frames -> mp4"),
        ]
    ):
        d.box(s, 8.6, 1.7 + i * 0.95, 4.2, 0.8, fill=PANEL, line=GREEN, text=f"{n}: {sub}", size=13)
    d.arrow(s, 8.05, 4.95, 8.55, 4.95, GOLD)
    d.text(
        s,
        "Offline: scenario.py, scripts/ (experiments, slides, report) read the same engine",
        0.55,
        5.8,
        12,
        0.5,
        size=14,
        color=DIM,
    )
    d.text(
        s,
        "Every AI move returns a Decision: action, mode, algorithm, nodes, ms, fuzzy inputs, rule strengths, "
        "path, explored cells, trace.",
        0.55,
        6.3,
        12.2,
        0.7,
        size=14,
    )

    # 7 algorithm table
    s = d.slide("Algorithms and where the game uses them")
    rows = [
        ["Algorithm", "Use in the game", "File"],
        ["DFS", "maze carving; dead ends; flood fill; Tom SWEEP", "search.py, maze.py"],
        ["Depth-limited search", "Jerry EVADE: safe 5-step paths", "search.py, agents.py"],
        ["Bidirectional BFS", "map validation; Tom AMBUSH meeting cell", "search.py"],
        ["Greedy best-first", "EASY Tom and Jerry; A* comparison", "search.py"],
        ["A*", "Tom HUNT; Jerry SNEAK / DASH / RUN_FOR_BRUNO", "search.py"],
        ["Minimax + alpha-beta", "HARD close range, both roles (depth 4)", "minimax.py"],
        ["MCTS", "NIGHTMARE target choice (300 iterations)", "mcts.py"],
        ["Fuzzy (Mamdani)", "picks Tom's and Jerry's mode every turn", "fuzzy.py"],
        ["IDDFS (bonus)", "benchmark only", "search.py"],
    ]
    d.table(s, rows, 0.55, 1.4, 12.2, col_w=[3, 6.5, 3], size=15, row_h=0.5, align_right_from=9)

    # 8 fuzzy
    s = d.slide(
        "Fuzzy logic: Tom's mode (Mamdani)",
        "Rules are data: (id, [(var, set)...], output). AND=min, clip, max, centroid 0..100.",
    )
    blocks = K.md_sections(K.DOCS / "ALGORITHMS.md")["Fuzzy logic (`fuzzy.py`)"]
    tom_rules = next(b.rows for b in blocks if b.kind == "table" and b.rows[0][0] == "Rule")  # type: ignore[index]
    d.table(
        s, tom_rules, 0.55, 1.4, 6.6, col_w=[0.7, 4.6, 1.2], size=11, row_h=0.36, align_right_from=9
    )
    d.bullets(
        s,
        [
            "Inputs: dist, age, bruno",
            "Output: pursuit 0..100 -> RETREAT / SWEEP / AMBUSH / HUNT",
            "bruno=Low added to T1-T6 so RETREAT is reachable",
        ],
        0.55,
        4.5,
        6.6,
        2.5,
        size=14,
    )
    d.picture(s, K.SCEN / "fuzzy_tom.png", 7.4, 1.25, 5.5, 5.6)

    # 9 A* vs greedy
    s = d.slide("A* vs greedy best-first")
    bench = K.bench_table()
    d.table(
        s,
        [bench[0]] + [r for r in bench[1:3]],
        0.55,
        1.4,
        5.6,
        col_w=[2.2, 1.2, 1.3, 0.9],
        size=12,
        row_h=0.4,
    )
    d.bullets(
        s,
        [
            "A*: f = g + h, Manhattan h, shortest path",
            "Greedy: f = h only, fewer nodes, longer path",
            "Same functions drive the game and the demo's C key",
            "Benchmark: 200 mazes, start to start",
        ],
        0.55,
        3.2,
        5.6,
        3.5,
        size=16,
    )
    d.picture(s, K.SCREENS / "demo_compare.png", 6.4, 1.3, 6.5, 5.5)

    # 10 minimax
    s = d.slide("Minimax with alpha-beta (depth 4)")
    d.picture(s, K.SCEN / "minimax_tree.png", 0.55, 1.35, 12.2, 3.9)
    d.bullets(
        s,
        [
            f"Position of the scenario: root value {sc['root_value']}, Tom's moves {sc['tom_values']}",
            f"Nodes at depth 4: plain minimax {sc['plain_nodes']}, alpha-beta {sc['ab_nodes']} (same value)",
            f"Agent runs iterative deepening d1..d4: {sc['tom_mm_nodes']} nodes",
            "Evaluation: -10 d(T,J) + 2 d(J,goal) - 3 escapes - 15 bruno - 8 stun + 5 dead end",
        ],
        0.55,
        5.4,
        12.2,
        1.9,
        size=15,
    )

    # 11 MCTS
    s = d.slide("MCTS: Tom's ambush target (information-set UCT)")
    d.picture(s, K.SCEN / "mcts_tree.png", 0.55, 1.3, 6.3, 5.7)
    mc = (K.SCEN / "mcts.md").read_text(encoding="utf-8")
    chosen = re.search(r"Chosen target \(most visits\): \*\*\((\d+,\d+)\)\*\*", mc)
    visits = re.search(rf"\| \({chosen.group(1)}\) \| (\d+) \|", mc) if chosen else None
    d.bullets(
        s,
        [
            f"{C.MCTS_ITERATIONS} iterations; UCB1 c = {C.MCTS_UCB_C}; playout <= {C.MCTS_PLAYOUT_TURNS} turns",
            "Each iteration samples where Jerry may be (determinization)",
            "Targets: keys, open exit, kennel, Jerry's last seen cell",
            "Reward: 1 if Jerry is caught in the playout",
            f"Scenario: target ({chosen.group(1)}) gets {visits.group(1)} of {C.MCTS_ITERATIONS} visits"
            if chosen and visits
            else "Scenario: see docs/scenario/mcts.md",
            f"Re-plan every {C.MCTS_REPLAN_TURNS} turns or on a new sighting",
        ],
        7.1,
        1.4,
        5.8,
        5.4,
        size=16,
    )

    # 12 heuristic calculation
    s = d.slide(
        "Heuristic calculation: A* in the scenario", "From docs/scenario/astar.md, turn 18."
    )
    tabs = [b for b in K.parse_md(K.SCEN / "astar.md") if b.kind == "table"]
    t1 = [r[:6] for r in tabs[0].rows]  # type: ignore[union-attr]
    t2 = [r[:6] for r in tabs[1].rows[:5]]  # type: ignore[union-attr]
    d.text(
        s,
        "Tom HUNT: (6,8) to Jerry (6,5), unit cost, h = Manhattan",
        0.55,
        1.3,
        12,
        0.4,
        size=14,
        color=DIM,
    )
    d.table(
        s,
        t1,
        0.55,
        1.7,
        12.2,
        col_w=[0.6, 1.2, 0.8, 3.8, 1.8, 1.4],
        size=12,
        row_h=0.36,
        align_right_from=9,
    )
    d.text(
        s,
        "Jerry RUN_FOR_BRUNO: (6,5) to kennel (8,1), danger-weighted (cell cost 1 + 4*risk), first 4 steps",
        0.55,
        3.9,
        12,
        0.4,
        size=14,
        color=DIM,
    )
    d.table(
        s,
        t2,
        0.55,
        4.3,
        12.2,
        col_w=[0.6, 1.2, 0.8, 3.8, 1.8, 1.4],
        size=12,
        row_h=0.36,
        align_right_from=9,
    )
    d.text(
        s,
        "f = g + h: g = cost so far, h = Manhattan distance to the goal. Ties: smaller h first.",
        0.55,
        6.5,
        12,
        0.4,
        size=14,
    )

    # 13-15 scenario
    s = d.slide(
        "Scenario 1/3: the position (turn 18)",
        "Fixed 13x13 map built by scenario.py; tests prove the markdown equals the live agents.",
    )
    d.picture(s, K.SCEN / "maze.png", 0.55, 1.3, 5.2, 5.8)
    d.bullets(
        s,
        [
            "Jerry (6,5), Tom (6,8): path distance 3",
            "2 of 3 keys taken; last key at (2,1)",
            "Bruno asleep in the kennel (8,1), 2 activations left",
            "Exit (3,11) locked",
            "Dead-end stub (7,5)-(8,5) below Jerry",
            "Junction (6,1): key north, kennel south",
            "Both agents are HARD and decide on the same snapshot",
        ],
        6.1,
        1.5,
        6.8,
        5.4,
        size=18,
    )

    s = d.slide(f"Scenario 2/3: Tom decides {sc['tom_action']}")
    steps = [
        "Sees Jerry at distance 3 (vision 5), age 0, Bruno unseen",
        f"Fuzzy: T1 = 1.00, centroid {sc['tom_centroid']}, mode {sc['tom_mode']}",
        "HUNT would run A*: 4 nodes, 3 steps, LEFT",
        f"Close range: minimax overrides, depth 4, {sc['tom_mm_nodes']} nodes",
        f"Values: {sc['tom_values']}",
        f"Tom is MAX: picks {sc['tom_action']}",
    ]
    d.bullets(s, [f"{i + 1}. {t}" for i, t in enumerate(steps)], 0.55, 1.4, 5.4, 5.6, size=16)
    mmtabs = [b for b in K.parse_md(K.SCEN / "minimax.md") if b.kind == "table"]
    d.table(
        s,
        mmtabs[1].rows,
        6.2,
        1.4,
        6.6,
        col_w=[3, 0.9, 1.1, 1.1, 1.1],
        size=11,
        row_h=0.32,
        align_right_from=9,
    )  # type: ignore[arg-type]
    d.picture(s, K.SCEN / "minimax_tree.png", 6.2, 4.5, 6.6, 2.5)

    s = d.slide(f"Scenario 3/3: Jerry decides {sc['jerry_action']}")
    steps = [
        "Sees Tom at distance 3, 1 key left, Bruno ready",
        f"Fuzzy: J3 = 1.00, centroid {sc['jerry_centroid']}, mode {sc['jerry_mode']}",
        "RUN_FOR_BRUNO would run A*: 7 nodes, 6 steps, LEFT",
        f"Close range: minimax overrides, depth 4, {sc['jerry_mm_nodes']} nodes",
        f"Values (Tom's view): {sc['jerry_values']}",
        f"Jerry is MIN: picks lowest, {sc['jerry_action']}",
    ]
    d.bullets(s, [f"{i + 1}. {t}" for i, t in enumerate(steps)], 0.55, 1.4, 5.4, 5.6, size=16)
    d.picture(s, K.SCEN / "fuzzy_jerry.png", 6.2, 1.25, 3.6, 3.0)
    d.picture(s, K.SCEN / "minimax_tree_jerry.png", 6.2, 4.4, 6.6, 2.6)
    d.text(
        s,
        "RIGHT walks into Tom, DOWN enters the dead end, WAIT lets Tom close in.",
        9.95,
        1.5,
        2.9,
        2.5,
        size=13,
        color=DIM,
    )

    # 16-19 experiments
    e1 = exp["E1"]["rows"]
    s = d.slide(f"Experiments: difficulty ladder ({games} games each)", first_sentence(concl["E1"]))
    d.picture(s, K.RESULTS / "E1.png", 0.55, 1.5, 6.0, 5.6)
    rows = [["Tom vs Jerry", "Jerry %", "turns", "Tom nodes", "Tom ms"]]
    for name, st in e1:
        rows.append(
            [
                name.replace("Tom ", "").replace("Jerry ", "J "),
                f"{100 * st['jerry_win']:.0f}",
                f"{st['avg_turns']:.1f}",
                f"{st['TOM']['avg_nodes']:.1f}",
                f"{st['TOM']['avg_ms']:.2f}",
            ]
        )
    d.table(s, rows, 6.8, 1.6, 6.0, col_w=[3, 1, 1, 1.3, 1.1], size=12, row_h=0.42)
    d.text(
        s,
        "Jerry % = Jerry's win rate. Seeds 0.." + str(games - 1) + ". Full tables: docs/RESULTS.md",
        6.8,
        5.5,
        6,
        0.8,
        size=12,
        color=DIM,
    )

    def pair(title: str, k1: str, k2: str) -> None:
        sl = d.slide(title)
        d.picture(sl, K.RESULTS / f"{k1}.png", 0.55, 1.3, 6.8, 2.9)
        d.picture(sl, K.RESULTS / f"{k2}.png", 0.55, 4.35, 6.8, 2.9)
        d.text(sl, first_sentence(concl[k1]), 7.7, 1.4, 5.1, 2.8, size=14)
        d.text(sl, first_sentence(concl[k2]), 7.7, 4.45, 5.1, 2.8, size=14)

    pair("Experiments: A* vs greedy, DLS depth", "E2", "E3")
    pair("Experiments: fuzzy director, minimax and MCTS", "E4", "E5")
    s = d.slide("Experiments: Bruno on vs off", first_sentence(concl["E6"]))
    d.picture(s, K.RESULTS / "E6.png", 0.55, 1.6, 6.8, 5.5)
    d.bullets(
        s,
        [
            "Bites only happen to Tom EASY: NORMAL+ retreats from a guarding Bruno (rule T7)",
            "For NORMAL+ Tom, Bruno works as deterrence",
            "Outcome causes recorded: capture, exit, timeout",
        ],
        7.6,
        1.8,
        5.2,
        4.5,
        size=16,
    )

    # 20 videos
    s = d.slide(
        "Speed-up gameplay videos (4x: 8 turns per second)",
        "Replay with: python main.py --seed S --tom T --jerry J "
        "and choose Watch AI vs AI, or regenerate with python record.py.",
    )
    names = {
        "bruno_saves_jerry": (
            "a_bruno_saves_jerry.mp4",
            "Bruno bites Tom while he is close to Jerry",
        ),
        "minimax_chase": (
            "b_minimax_close_chase.mp4",
            "both sides choose by minimax at close range",
        ),
        "fuzzy_switch": (
            "c_fuzzy_mode_switch.mp4",
            "Tom's fuzzy mode switches (4 turns/s, panel readable)",
        ),
        "full_game": ("d_full_game_hard_vs_hard.mp4", "one complete HARD vs HARD game"),
    }
    rows = [["File (videos/)", "Shows", "Seed", "Tom vs Jerry", "Turns"]]
    for key, (fn, what) in names.items():
        v = seeds[key]
        rows.append(
            [fn, what, str(v["seed"]), f"{v['tom']} vs {v['jerry']}", f"{v['from']}-{v['to']}"]
        )
    d.table(
        s,
        rows,
        0.55,
        1.5,
        12.2,
        col_w=[3.4, 5.4, 0.8, 1.9, 1.1],
        size=13,
        row_h=0.6,
        align_right_from=2,
    )
    d.text(
        s,
        "Seeds found by scanning 200 headless games per setup (scripts/find_demo_seeds.py); notes in docs/DEMO.md.",
        0.55,
        4.9,
        12,
        0.6,
        size=14,
        color=DIM,
    )

    # 21 conclusion
    s = d.slide("Conclusion")
    e5 = dict(exp["E5"]["rows"])
    e1d = dict(exp["E1"]["rows"])
    hn = 100 * e1d["Tom HARD vs Jerry NORMAL"]["jerry_win"]
    hh = 100 * e1d["Tom HARD vs Jerry HARD"]["jerry_win"]
    d.bullets(
        s,
        [
            "All eight techniques do real work in the game and show in the UI",
            f"NORMAL Jerry wins {100 * dict(exp['E1']['rows'])['Tom HARD vs Jerry NORMAL']['jerry_win']:.0f}% against HARD Tom "
            f"({games} games); minimax on or off is within noise (E5: "
            f"{100 * e5['Tom HARD without minimax']['jerry_win']:.0f}% vs {100 * e5['Tom HARD (minimax on)']['jerry_win']:.0f}%)",
            "HARD's strength comes mostly from the key-vanish belief update",
            f"Limits: Jerry's win rate against HARD Tom is {hn:.0f}-{hh:.0f}%, at the low end of the 35-60% target; "
            "MCTS adds little over HARD",
            "Next: stronger MCTS playouts, learned weights for the evaluation, larger mazes",
        ],
        0.55,
        1.5,
        12.2,
        5.4,
        size=20,
    )
    return d


def main() -> None:
    d = build()
    OUT.parent.mkdir(exist_ok=True)
    d.prs.save(OUT)
    print(f"{OUT}: {d.n} slides, {len(d.images)} images")


if __name__ == "__main__":
    main()
