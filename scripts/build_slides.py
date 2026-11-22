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

sys.path.insert(0, str(K.ROOT))
import scenario  # noqa: E402

C = K.C
OUT = K.ROOT / "slides" / "cheese_heist.pptx"

# Light theme. Ink is the maze-wall navy of the figures, so slides and images read as one set.
BG, PANEL, LINE = RGBColor(0xF4, 0xF6, 0xF9), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0xD6, 0xDC, 0xE5)
TEXT, DIM = RGBColor(0x1E, 0x2A, 0x3E), RGBColor(0x5E, 0x6A, 0x7D)
GOLD, BLUE, GREEN, ORANGE, RED = (
    RGBColor(0xE0, 0x9F, 0x12),  # cheese
    RGBColor(0x2F, 0x6B, 0xD0),  # Jerry
    RGBColor(0x1E, 0x9E, 0x5A),  # chosen path
    RGBColor(0xD9, 0x66, 0x1A),  # Tom
    RGBColor(0xC0, 0x39, 0x2B),
)
HEAD_FILL, ZEBRA = RGBColor(0xE4, 0xE9, 0xF0), RGBColor(0xF8, 0xF9, 0xFB)
TITLE_FONT = "Bahnschrift"
FONT = "Segoe UI"
W, H = 13.333, 7.5


class Deck:
    """Thin helper around python-pptx: light slides, titles, bullets, tables, pictures."""

    def __init__(self) -> None:
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.n = 0
        self.images: list[Path] = []
        self.section: tuple[str, RGBColor] = ("", TEXT)

    def rect(self, s, x, y, w, h, fill):  # type: ignore[no-untyped-def]
        r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        r.fill.solid()
        r.fill.fore_color.rgb = fill
        r.line.fill.background()
        return r

    def slide(self, title: str, notes: str = "", subtitle: str = ""):  # type: ignore[no-untyped-def]
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.n += 1
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = BG
        name, col = self.section
        if title:
            self.rect(s, 0, 0, 0.16, H, col)  # chapter corridor
            self.text(
                s, title, 0.55, 0.3, W - 1.1, 0.75, size=30, bold=True, color=TEXT, font=TITLE_FONT
            )
            self.rect(s, 0.55, 1.02, W - 1.1, 0.015, LINE)
            self.text(s, name, 0.55, H - 0.42, 6, 0.3, size=10, color=col, bold=True)
            self.text(
                s,
                str(self.n),
                W - 1.55,
                H - 0.42,
                1.0,
                0.3,
                size=10,
                color=DIM,
                align=PP_ALIGN.RIGHT,
            )
        if subtitle:
            self.text(s, subtitle, 0.55, 1.1, W - 1.1, 0.4, size=14, color=DIM)
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
            r0.font.size, r0.font.color.rgb, r0.font.name = Pt(size - 6), self.section[1], FONT
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
        return c

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
                cell.fill.fore_color.rgb = HEAD_FILL if i == 0 else (PANEL if i % 2 else ZEBRA)
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
                r.font.color.rgb = TEXT
        return gf


def _numeric(v: str) -> bool:
    return bool(re.fullmatch(r"[-+]?[\d.,]+%?", v))


# ------------------------------------------------------------------ the deck


def flow(d: Deck, s, labels: list[str], y: float, h: float = 1.0) -> None:  # type: ignore[no-untyped-def]
    """Row of boxes joined by arrows; the last box (the outcome) is filled in the chapter colour."""
    n = len(labels)
    gap = 0.35
    w = (12.2 - gap * (n - 1)) / n
    col = d.section[1]
    for i, lab in enumerate(labels):
        x = 0.55 + i * (w + gap)
        last = i == n - 1
        d.box(
            s,
            x,
            y,
            w,
            h,
            fill=col if last else PANEL,
            line=col,
            text=lab,
            size=12,
            color=PANEL if last else TEXT,
            bold=last,
        )
        if not last:
            d.arrow(s, x + w + 0.03, y + h / 2, x + w + gap - 0.03, y + h / 2, DIM)


def steps_slide(  # type: ignore[no-untyped-def]
    d: Deck, title: str, steps: list[str], right=None, caption: str = "", size: int = 15
):
    """Numbered explanation on the left; optional picture with a caption on the right."""
    s = d.slide(title)
    w = 6.0 if right else 12.2
    d.bullets(s, [f"{i + 1}. {t}" for i, t in enumerate(steps)], 0.55, 1.35, w, 5.7, size=size)
    if right:
        d.picture(s, right, 6.8, 1.3, 6.1, 4.4)
        d.text(s, caption, 6.8, 5.8, 6.1, 1.1, size=11, color=DIM)
    return s


def build() -> Deck:  # noqa: PLR0915
    d = Deck()
    sc = K.scenario_facts()

    # 1 title: the real turn-18 scenario maze, drawn cell by cell
    s = d.slide("")
    d.text(s, "Cheese Heist", 0.8, 2.0, 6.4, 1.2, size=58, bold=True, color=TEXT, font=TITLE_FONT)
    d.text(s, "How every move is decided, step by step", 0.8, 3.2, 6.2, 0.6, size=22)
    d.text(
        s,
        "Fuzzy logic, A*, greedy best-first, DFS, depth-limited search, bidirectional BFS, "
        "minimax with alpha-beta and MCTS, traced on one real game position.",
        0.8,
        3.95,
        5.9,
        1.2,
        size=15,
        color=DIM,
    )
    d.rect(s, 0.8, 5.45, 0.9, 0.06, GOLD)
    d.text(s, "Artificial Intelligence lab, final project", 0.8, 5.65, 6, 0.4, size=13, color=DIM)
    grid = [ln for ln in scenario.MAP.strip().splitlines()]
    cell, gx, gy = 0.44, 7.25, 0.9
    marks = {
        "T": (ORANGE, "T"),
        "J": (BLUE, "J"),
        "K": (GOLD, "K"),
        "E": (RED, "E"),
        "H": (RGBColor(0x8D, 0x6E, 0x63), "B"),
    }
    for r, line in enumerate(grid):
        for c, ch in enumerate(line):
            x, y = gx + c * cell, gy + r * cell
            d.rect(s, x, y, cell, cell, TEXT if ch == "#" else PANEL)
            if ch in marks:
                col, lab = marks[ch]
                d.box(
                    s,
                    x + 0.05,
                    y + 0.05,
                    cell - 0.1,
                    cell - 0.1,
                    fill=col,
                    line=col,
                    shape=MSO_SHAPE.OVAL,
                    text=lab,
                    size=11,
                    color=PANEL,
                    bold=True,
                )
    d.text(
        s,
        "Turn 18: Tom 3 steps behind Jerry, one key left, Bruno asleep",
        gx,
        gy + len(grid) * cell + 0.08,
        len(grid) * cell,
        0.4,
        size=11,
        color=DIM,
        align=PP_ALIGN.CENTER,
    )

    d.section = ("The game", TEXT)
    # 2 overview
    s = d.slide("Game overview")
    d.bullets(
        s,
        [
            "Jerry (mouse) collects 3 keys, then runs to the exit",
            "Tom (cat) hunts her; Bruno (dog) is Jerry's bodyguard",
            f"{C.DEFAULT_SIZE}x{C.DEFAULT_SIZE} maze generated from a seed (DFS + loops)",
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
    d.picture(s, K.SCREENS / "spectator.png", 5.7, 1.3, 7.1, 4.6)
    d.text(
        s,
        "AI vs AI, seed 7, turn 31, both HARD. Green dots: each AI's planned path; light blue: "
        "cells its search explored. Top bar names each level's signature algorithm; the panel "
        "shows what ran this turn (Tom AMBUSH with bidirectional BFS, Jerry SNEAK with A*).",
        5.7,
        5.95,
        7.1,
        1.0,
        size=11,
        color=DIM,
    )

    # 3 rules
    s = d.slide("Rules")
    flow(
        d,
        s,
        [
            "Jerry acts\nthen win check",
            "Tom acts\n(skipped if stunned)\nthen win check",
            "Bruno acts\n(scripted FSM)",
            f"Timers tick, turn + 1\n(Tom wins after\nturn {C.TURN_LIMIT})",
        ],
        1.5,
    )
    d.bullets(
        s,
        [
            "Actions: UP, DOWN, LEFT, RIGHT, WAIT; 1 cell; walls block; Tom is not faster",
            f"{C.NUM_KEYS} keys; the exit opens on the 3rd key and an ALARM tells Tom where it is",
            "Same cell after any move = capture (Tom wins); Jerry on the open exit wins first",
            f"Fairness: best start -> 3 keys -> exit walk <= {C.MAX_KEY_TOUR} steps, checked by bidirectional BFS",
            "Same seed + same actions = same game",
        ],
        0.55,
        3.2,
        12.2,
        3.8,
        size=19,
    )

    # 4 fog
    s = d.slide("Mechanics: fog of war")
    d.bullets(
        s,
        [
            f"Vision = BFS path distance <= {C.VISION_RADIUS}; walls block sight",
            "An agent gets only what it may know: its position, visible opponent, keys, exit",
            "Tom smells the keys; learns the exit only at the ALARM",
            "Agents remember where and when they last saw the opponent (age = turns since)",
            "So every algorithm below works on incomplete information",
        ],
        0.55,
        1.4,
        5.2,
        5.0,
        size=18,
    )
    d.picture(s, K.SCREENS / "fog_view.png", 5.9, 1.3, 6.9, 4.6)
    d.text(
        s,
        "Human plays Jerry, turn 22. Only cells within 5 steps are lit; Tom is drawn because he "
        "is inside that range. Keys, exit and kennel stay drawn because Jerry knows them.",
        5.9,
        5.95,
        6.9,
        1.0,
        size=11,
        color=DIM,
    )

    # 5 Bruno FSM
    s = d.slide(
        "Mechanics: Bruno's finite-state machine",
        "Scripted; one BFS step per round; never harms Jerry.",
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
        lx=-1.2,
        ly=0.2,
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

    d.section = ("How a move is decided", GOLD)
    # 6 algorithm table
    s = d.slide("Eight algorithms and what each one decides")
    rows = [
        ["Algorithm", "Question it answers in the game"],
        ["Fuzzy logic (Mamdani)", "Which mode should Tom / Jerry use this turn?"],
        [
            "A*",
            "Shortest, risk-aware route to a target (Tom HUNT; Jerry SNEAK, DASH, run to Bruno)",
        ],
        ["Greedy best-first", "Fast but not optimal route (EASY level; compared with A*)"],
        ["DFS", "Carve the maze; find dead ends and open space; Tom SWEEP order"],
        ["Depth-limited search", "Which 5-step escape is safe for Jerry (EVADE)?"],
        ["Bidirectional BFS", "Is the map connected? Where should Tom wait in ambush?"],
        ["Minimax + alpha-beta", "Best move when the two are close (depth 4, both roles)"],
        ["MCTS", "Which target should Tom ambush / which key should Jerry take? (NIGHTMARE)"],
    ]
    d.table(s, rows, 0.55, 1.4, 12.2, col_w=[3.2, 9], size=16, row_h=0.55, align_right_from=9)

    # 7 pipeline
    s = d.slide("How one AI move is decided: the pipeline")
    flow(
        d,
        s,
        [
            "1. Observe\nonly what the\nagent may see",
            "2. Fuzzy logic\ninputs -> rules\n-> mode",
            "3. Mode picks\nan algorithm",
            "4. Algorithm\nreturns a path",
            "5. First step\nof the path\n= action",
        ],
        1.5,
    )
    d.box(
        s,
        3.6,
        3.1,
        6.2,
        0.9,
        fill=PANEL,
        line=ORANGE,
        text="Close range (opponent visible, path distance <= 4, HARD+):\nminimax with alpha-beta replaces step 3-4",
        size=13,
    )
    d.arrow(s, 6.7, 2.55, 6.7, 3.1, ORANGE)
    d.bullets(
        s,
        [
            "Fuzzy logic = the strategist: decides WHAT to do (hunt, ambush, sweep, retreat / sneak, evade, dash)",
            "Search algorithms = the pathfinders: decide HOW to do it, one cell at a time",
            "Minimax = the tactician when a capture is only a few moves away",
            "MCTS (NIGHTMARE) = long-range planner that chooses the target for AMBUSH or SNEAK",
            "Nothing is random in the loop: same observation -> same action",
        ],
        0.55,
        4.3,
        12.2,
        2.8,
        size=16,
    )

    # 7b one full turn, both sides, animated (scripts/slides_turn.py)
    from slides_turn import turn_chapter

    turn_chapter(d, sc)

    # 8 fuzzy method
    steps_slide(
        d,
        "Fuzzy logic: the Mamdani steps",
        [
            "Fuzzify: turn each crisp input into membership degrees with triangle / trapezoid curves (turn 18: dist 3 -> Near 1.00, Mid 0, Far 0)",
            "Rules: each rule ANDs its conditions with min -> rule strength",
            "Implication: clip the rule's output set at its strength",
            "Aggregate: take the max of all clipped output sets",
            "Defuzzify: centroid of the aggregated shape over 0..100 -> one number",
            "Mode = output set with the highest membership at that centroid",
            "Rules are data, so every decision can be explained as 'rule T1 fired at 1.00'",
        ],
        right=K.SCEN / "fuzzy_tom.png",
        size=15,
    )

    # 9 Tom fuzzy
    s = d.slide("Tom's fuzzy controller")
    d.table(
        s,
        [
            ["Rule", "IF", "THEN"],
            ["T1", "dist Near AND age Fresh AND bruno Low", "HUNT"],
            ["T2", "dist Mid AND age Fresh AND bruno Low", "HUNT"],
            ["T3", "dist Far AND age Fresh AND bruno Low", "AMBUSH"],
            ["T4", "dist Near AND age Stale AND bruno Low", "HUNT"],
            ["T5", "age Stale AND bruno Low", "AMBUSH"],
            ["T6", "age Lost AND bruno Low", "SWEEP"],
            ["T7", "bruno High", "RETREAT"],
        ],
        0.55,
        1.4,
        7.0,
        col_w=[0.7, 4.8, 1.5],
        size=13,
        row_h=0.4,
        align_right_from=9,
    )
    d.bullets(
        s,
        [
            "dist: path distance to Jerry (or to where she was last seen)",
            "age: turns since Tom last saw Jerry",
            "bruno: how close an awake Bruno is to Tom",
            "Output pursuit 0..100: RETREAT, SWEEP, AMBUSH, HUNT",
        ],
        0.55,
        4.8,
        7.0,
        2.4,
        size=15,
    )
    d.picture(s, K.SCEN / "fuzzy_tom.png", 7.8, 1.25, 5.1, 5.7)

    # 10 Jerry fuzzy
    s = d.slide("Jerry's fuzzy controller")
    d.table(
        s,
        [
            ["Rule", "IF", "THEN"],
            ["J1", "danger Safe AND keys_left Some", "SNEAK"],
            ["J2", "danger Medium AND keys_left Some", "EVADE"],
            ["J3", "danger Close AND bruno_ready Yes", "RUN_FOR_BRUNO"],
            ["J4", "danger Close AND bruno_ready No", "EVADE"],
            ["J5", "keys_left Done AND danger Safe", "DASH"],
            ["J6", "keys_left Done AND danger Medium", "DASH"],
            ["J7", "keys_left Done AND danger Close", "EVADE"],
        ],
        0.55,
        1.4,
        7.0,
        col_w=[0.7, 4.3, 2.0],
        size=13,
        row_h=0.4,
        align_right_from=9,
    )
    d.bullets(
        s,
        [
            "danger: path distance to Tom (30 if unseen for more than 6 turns)",
            "keys_left: 0..3; bruno_ready: Bruno asleep with activations left",
            "Output urgency 0..100: SNEAK, EVADE, RUN_FOR_BRUNO, DASH",
        ],
        0.55,
        4.8,
        7.0,
        2.4,
        size=15,
    )
    d.picture(s, K.SCEN / "fuzzy_jerry.png", 7.8, 1.25, 5.1, 5.7)

    # 11 mode -> algorithm
    s = d.slide("From mode to algorithm: what each mode does")
    d.table(
        s,
        [
            ["Role", "Mode", "Algorithm", "Action taken"],
            ["Tom", "HUNT", "A*", "first step of shortest path to Jerry / last seen cell"],
            [
                "Tom",
                "AMBUSH",
                "Bidirectional BFS",
                "walk toward the likely next key, stop where Tom arrives first, WAIT",
            ],
            [
                "Tom",
                "SWEEP",
                "DFS",
                "go to nearest recently unseen cell, near Jerry's last position first",
            ],
            ["Tom", "RETREAT", "BFS distance map", "step that maximises distance from Bruno"],
            [
                "Jerry",
                "SNEAK",
                "A* (danger-weighted)",
                "step along the safest path to the nearest key",
            ],
            [
                "Jerry",
                "RUN_FOR_BRUNO",
                "A* (danger-weighted)",
                "step toward the kennel to wake Bruno",
            ],
            ["Jerry", "EVADE", "DLS depth 5", "first step of the best safe 5-step path"],
            ["Jerry", "DASH", "A* (danger-weighted)", "step toward the open exit"],
            ["Both", "close range", "Minimax alpha-beta", "best of 5 moves looking 4 plies ahead"],
        ],
        0.55,
        1.4,
        12.2,
        col_w=[0.9, 1.8, 2.6, 6.9],
        size=14,
        row_h=0.5,
        align_right_from=9,
    )

    d.section = ("Search algorithms", BLUE)
    # 12 A*
    steps_slide(
        d,
        "A*: how the next step is found",
        [
            "Open list holds cells to try, each with f = g + h",
            "g = cost paid from start; h = Manhattan distance to goal (never overestimates, so A* is optimal)",
            "Pop the cell with the smallest f; if it is the goal, stop",
            "Otherwise expand its 4 neighbours, update g, push into the open list",
            "Rebuild the path by following parents; the action is its first step",
            "Tom: every cell costs 1 (pure shortest path)",
            "Jerry: cell cost = 1 + 4 x risk, risk = max(0, 6 - d_tom) / 6, +3 for dead ends when Tom is within 8, so she routes around Tom",
        ],
        right=K.SCREENS / "demo_1_astar.png",
        caption="Algorithm demo, seed 7, paused at expansion 84 of 153: blue = expanded, yellow = open list. The cell just expanded is (11,9) with g 19, h 16, f 35.",
        size=14,
    )
    s = d.slide("A*: heuristic calculation, turn 18")
    tabs = [b for b in K.parse_md(K.SCEN / "astar.md") if b.kind == "table"]
    t1 = [r[:6] for r in tabs[0].rows]  # type: ignore[union-attr]
    t2 = [r[:6] for r in tabs[1].rows[:5]]  # type: ignore[union-attr]
    d.text(
        s,
        "Tom HUNT: (6,8) to Jerry (6,5), cost 1 per cell, h = Manhattan",
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
        "Jerry to kennel (8,1): danger-weighted cost, first 4 steps",
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
        "Each row: the cell A* expands, its g, h, f = g + h and the open-list size. Smallest f is popped next.",
        0.55,
        6.5,
        12,
        0.5,
        size=14,
    )

    # 13 greedy
    s = d.slide("Greedy best-first vs A*")
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
            "Greedy orders the open list by h only: always walks toward the goal",
            "A* orders by g + h: also remembers the cost already paid",
            "Greedy expands fewer cells but can return a longer path (right: 75 vs 153 nodes, 49 vs 47 steps)",
            "EASY Tom uses greedy; the other levels use A*",
        ],
        0.55,
        3.2,
        5.6,
        3.8,
        size=16,
    )
    d.picture(s, K.SCREENS / "demo_compare.png", 6.4, 1.3, 6.5, 5.5)

    # 14 DFS
    steps_slide(
        d,
        "DFS: three jobs in the game",
        [
            "Maze generation (recursive backtracker): from a cell, go to a random unvisited neighbour, knock down the wall, recurse; backtrack at a dead end. Then ~8% of walls are removed to make loops",
            "Dead-end cells: floor cells with one open neighbour. Jerry avoids them when Tom is near (+3 cost, -5 score)",
            "Flood fill: DFS counts the cells reachable from a spot without crossing a given set; used as 'open space' in Jerry's EVADE score",
            "Tom SWEEP: when Tom has lost Jerry, DFS visits floor cells not seen recently, nearest first, preferring cells near Jerry's last known position",
            "DFS goes deep first and uses a stack, so it finds a path fast but not the shortest one",
        ],
        right=K.SCREENS / "demo_3_dfs.png",
        caption="Algorithm demo, same S and G, paused at expansion 94 of 172. DFS dives down one corridor at a time instead of spreading evenly like BFS.",
        size=14,
    )

    # 15 bidirectional
    steps_slide(
        d,
        "Bidirectional BFS: validation and ambush",
        [
            "Run BFS from both ends at once, one layer each; stop when the two frontiers touch",
            "The touching cell is the meeting cell; joining both half-paths gives the shortest path",
            "Each side explores about half the depth, so far fewer cells than one-sided BFS",
            "Map validation: every key, exit and kennel must be reachable from both start cells, else the maze is regenerated",
            "Tom AMBUSH: target = the unclaimed key nearest Jerry's last seen cell (or the exit once open)",
            "Bidirectional BFS gives the Tom-to-target path; Tom walks it and stops at the last cell he reaches no later than Jerry's estimated arrival (tom_dist <= jerry_dist - 1), then WAITs",
        ],
        right=K.SCREENS / "demo_5_bidirectional.png",
        caption="Algorithm demo, paused at 81 of 148 expansions: blue wave from S, orange wave from G, one layer each in turn. The goal side sits in a corridor, so its layers are small.",
        size=14,
    )

    # 16 DLS
    steps_slide(
        d,
        "Depth-limited search: Jerry EVADE (depth 5)",
        [
            "DFS that stops at depth 5: list every 5-step path from Jerry, no revisits",
            "A path is SAFE if for each step t the cell is farther from Tom than t steps: d_tom(cell) > t (Jerry arrives first)",
            "Score = d_tom(last cell) + 0.5 x open space behind it - 5 if it ends in a dead end",
            "Take the first step of the best safe path",
            "No safe path? Pick the neighbour that maximises d_tom",
            "Cutoff = path stopped by the depth limit; failure = no path found",
        ],
        right=K.SCREENS / "demo_4_dls.png",
        caption="Algorithm demo: depth limit 5, 19 nodes, 4 cutoff cells (red) where the limit stopped the search. Tom is far away at G, so all 4 five-step paths are safe; magenta = best.",
        size=14,
    )
    s = d.slide("DLS in the scenario (turn 18)")
    d.table(
        s,
        [
            ["Path (5 steps)", "Safe?", "d_tom(last)", "Open space", "Score"],
            ["(6,4) (6,3) (6,2) (6,1) (5,1)", "yes", "8", "44", "30"],
            ["(6,4) (6,3) (6,2) (6,1) (7,1)", "yes", "8", "44", "30"],
            ["(6,6) (6,7) (6,8) (6,9) (6,10)", "no: step 2 cell has d_tom 1 <= 2", "2", "44", "-"],
        ],
        0.55,
        1.5,
        12.2,
        col_w=[4.2, 3.8, 1.4, 1.4, 1.4],
        size=14,
        row_h=0.55,
        align_right_from=2,
    )
    d.bullets(
        s,
        [
            "Score for path 1 = 8 + 0.5 x 44 = 30; the dead-end stub below Jerry never gives a 5-step path",
            "Best safe path starts LEFT: away from Tom, toward open space",
            "In this snapshot minimax overrides EVADE because Tom is within 4; the table shows what EVADE would pick",
        ],
        0.55,
        4.2,
        12.2,
        2.5,
        size=17,
    )

    d.section = ("Adversarial and strategic planning", ORANGE)
    # 17 minimax
    steps_slide(
        d,
        "Minimax with alpha-beta: how it picks a move",
        [
            "Look 4 plies ahead: Tom, Jerry, Tom, Jerry (Jerry first for her own call); Bruno moves after each round",
            "Tom = MAX, Jerry = MIN, all values from Tom's view; capture = +1000 - ply, Jerry on open exit = -1000 + ply",
            "Leaf value E = -10 d(T,J) + 2 d(J,goal) - 3 escapes - 15 bruno near Tom - 8 stun left + 5 if Jerry in dead end",
            "MAX picks the largest child value, MIN the smallest, back up to the root",
            "Alpha-beta: alpha = best MAX can force, beta = best MIN can force; when alpha >= beta the branch is cut, same answer, fewer nodes",
            "Moves are ordered (closer to the opponent first, WAIT last) so cuts happen early",
            "Iterative deepening d1..d4 with a 20000-node cap keeps timing predictable",
        ],
        size=18,
    )
    s = d.slide("Minimax search tree, turn 18")
    d.picture(s, K.SCEN / "minimax_tree.png", 0.55, 1.35, 12.2, 3.9)
    d.bullets(
        s,
        [
            f"Root value {sc['root_value']}; Tom's moves score {sc['tom_values']} -> MAX picks {sc['tom_action']}",
            f"Depth 4 nodes: plain minimax {sc['plain_nodes']}, alpha-beta {sc['ab_nodes']}; both return the same value",
            "Grey boxes were pruned (alpha >= beta). A pruned branch shows a bound, not its exact value: RIGHT is drawn -28 but searched fully it is -44",
        ],
        0.55,
        5.4,
        12.2,
        1.9,
        size=16,
    )

    # 18 MCTS
    steps_slide(
        d,
        "MCTS: how the strategic target is chosen",
        [
            "Candidates: Tom picks among remaining keys, open exit, kennel, Jerry's last seen cell; Jerry picks the next key",
            "Determinization: Tom cannot see Jerry, so each iteration guesses her cell among those reachable since last seen",
            "Selection: descend the tree with UCB1 = wins/visits + 1.4 x sqrt(ln N / visits)",
            "Expansion: add one new child (a candidate target)",
            "Playout: simulate up to 20 turns with a cheap policy (Tom walks to the target, Jerry heads for a key)",
            "Backpropagation: reward 1 if Tom captured Jerry in the playout, 0 otherwise, added up the tree",
            "After 300 iterations pick the child with the most visits",
        ],
        right=K.SCREENS / "demo_7_mcts.png",
        caption="Algorithm demo: Jerry last seen 3 turns ago. Magenta dots = 10 cells sampled as her possible position. After 300 iterations key B (11,9) has the most visits (134), so Tom picks it.",
        size=14,
    )
    s = d.slide("MCTS search tree, turn 18")
    d.picture(s, K.SCEN / "mcts_tree.png", 0.55, 1.3, 6.3, 5.7)
    mc = (K.SCEN / "mcts.md").read_text(encoding="utf-8")
    rows_ = re.findall(
        r"\| \((\d+,\d+)\) \| (\d+) \| (\d+) \| ([\d.]+) \| [\d.]+ \| ([\d.]+) \|", mc
    )[:3]
    d.table(
        s,
        [["Target", "Visits", "Wins", "Win rate", "UCB1"]]
        + [[f"({a})", b, c, e, f] for a, b, c, e, f in rows_],
        7.1,
        1.5,
        5.7,
        col_w=[1.4, 1, 1, 1.3, 1],
        size=13,
        row_h=0.45,
    )
    d.bullets(
        s,
        [
            "Most visits = most promising: key (2,1) was simulated 260 of 300 times and won 250",
            "UCB1 adds an exploration bonus, so rarely tried targets still get checked",
        ],
        7.1,
        3.6,
        5.7,
        3.2,
        size=16,
    )

    d.section = ("Scenario trace, turn 18", GREEN)
    # scenario
    s = d.slide("Scenario: the position (turn 18)")
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

    s = d.slide(f"Scenario: Tom decides {sc['tom_action']}, step by step")
    flow(
        d,
        s,
        [
            "Observe\nJerry at dist 3\nage 0, no Bruno",
            f"Fuzzy\nT1 = 1.00\ncentroid {sc['tom_centroid']}",
            f"Mode\n{sc['tom_mode']}",
            "A* would give\nLEFT (4 nodes,\n3 steps)",
            f"Minimax\noverrides\n{sc['tom_mm_nodes']} nodes",
            f"Action\n{sc['tom_action']}",
        ],
        1.4,
        h=1.2,
    )
    mmtabs = [b for b in K.parse_md(K.SCEN / "minimax.md") if b.kind == "table"]
    d.table(
        s,
        mmtabs[1].rows,
        0.55,
        3.0,
        6.6,
        col_w=[3, 0.9, 1.1, 1.1, 1.1],
        size=11,
        row_h=0.32,
        align_right_from=9,
    )  # type: ignore[arg-type]
    d.bullets(
        s,
        [
            "Why fuzzy says HUNT: Jerry is Near and Fresh, Bruno asleep (Low) -> rule T1 at full strength",
            "Why minimax overrides: distance 3 <= 4 and Jerry visible, so the tactical search decides",
            f"Why {sc['tom_action']}: highest value for MAX among his three legal moves (UP and DOWN are walls)",
        ],
        7.4,
        3.0,
        5.5,
        4.0,
        size=15,
    )

    s = d.slide(f"Scenario: Jerry decides {sc['jerry_action']}, step by step")
    flow(
        d,
        s,
        [
            "Observe\nTom at dist 3\n1 key left\nBruno ready",
            f"Fuzzy\nJ3 = 1.00\ncentroid {sc['jerry_centroid']}",
            f"Mode\n{sc['jerry_mode']}",
            "A* would give\nLEFT (7 nodes,\n6 steps)",
            f"Minimax\noverrides\n{sc['jerry_mm_nodes']} nodes",
            f"Action\n{sc['jerry_action']}",
        ],
        1.4,
        h=1.2,
    )
    d.picture(s, K.SCEN / "minimax_tree_jerry.png", 0.55, 3.0, 7.2, 4.0)
    d.bullets(
        s,
        [
            "Why fuzzy says RUN_FOR_BRUNO: danger Close and Bruno ready -> J3",
            f"Jerry is MIN: picks the lowest value for Tom: {sc['jerry_values']}",
            "RIGHT (0) steps toward Tom, DOWN (-8) enters the dead end, WAIT (-9) lets Tom close in; LEFT (-24) is lowest",
            "Both modes and minimax agree on LEFT",
        ],
        8.0,
        3.0,
        4.9,
        4.0,
        size=15,
    )

    d.section = ("Summary", TEXT)
    # summary
    s = d.slide("Summary: who decides what")
    d.table(
        s,
        [
            ["Decision", "Algorithm", "Why this one"],
            [
                "Which mode this turn",
                "Fuzzy logic",
                "Soft, explainable rules over fuzzy ideas like 'near' and 'stale'",
            ],
            [
                "Shortest / safest route",
                "A*",
                "Optimal with an admissible heuristic; costs can encode danger",
            ],
            [
                "Where to wait in ambush",
                "Bidirectional BFS",
                "Meeting cell between Tom and target, fewer nodes",
            ],
            ["Where to search when lost", "DFS", "Cheap exhaustive coverage of unseen cells"],
            [
                "Safe 5-step escape",
                "Depth-limited search",
                "Bounded lookahead with a safety test per step",
            ],
            [
                "Close-range fight",
                "Minimax + alpha-beta",
                "Adversarial: both sides play their best",
            ],
            ["Long-range target", "MCTS", "Handles hidden information by sampling"],
        ],
        0.55,
        1.4,
        12.2,
        col_w=[3, 3, 6.2],
        size=15,
        row_h=0.6,
        align_right_from=9,
    )
    return d


def main() -> None:
    d = build()
    OUT.parent.mkdir(exist_ok=True)
    d.prs.save(OUT)
    print(f"{OUT}: {d.n} slides, {len(d.images)} images")


if __name__ == "__main__":
    main()
