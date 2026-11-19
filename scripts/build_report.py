"""Build report/cheese_heist_report.docx (python-docx, A4, 11 pt) and convert it to PDF if possible.

Content is read from the repo: docs/RULES.md, docs/ALGORITHMS.md, docs/scenario/*.md (tables and
images), results/experiments.json, results/demo_seeds.json, config.py and the source (line
numbers via ast). PDF: soffice if on PATH, else Microsoft Word through COM (Windows), else the
DOCX is kept and a message says so.

Usage: python scripts/build_report.py [--no-pdf]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content as K  # noqa: E402

C = K.C
OUT_DIR = K.ROOT / "report"
DOCX = OUT_DIR / "cheese_heist_report.docx"
PDF = OUT_DIR / "cheese_heist_report.pdf"
TEXT_W = 16.0  # cm, A4 with 2.5 cm margins


# ------------------------------------------------------------------ docx helpers


class Report:
    """Wraps a python-docx Document with numbered headings, captions and markdown rendering."""

    def __init__(self) -> None:
        self.doc = Document()
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.5)
        sec.top_margin = sec.bottom_margin = Cm(2.3)
        st = self.doc.styles["Normal"]
        st.font.name, st.font.size = "Calibri", Pt(11)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.line_spacing = 1.08
        for name, size in (("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)):
            h = self.doc.styles[name]
            h.font.name, h.font.size, h.font.bold = "Calibri", Pt(size), True
            h.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
            h.paragraph_format.space_before = Pt(14 if name != "Heading 1" else 0)
            h.paragraph_format.keep_with_next = True
        cap = self.doc.styles["Caption"]
        cap.font.name, cap.font.size, cap.font.italic = "Calibri", Pt(9.5), True
        cap.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        self.counters = [0, 0]
        self.fig = 0
        self.tab = 0
        self.toc: list[tuple[int, str]] = []
        self.images: list[Path] = []
        self.footer()

    # ---- page furniture
    def footer(self) -> None:
        p = self.doc.sections[0].footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("Cheese Heist report   |   page ")
        r.font.size = Pt(9)
        self.field(p, "PAGE", size=9)

    @staticmethod
    def field(par, instr: str, size: float = 11, cached: str = "1") -> None:  # type: ignore[no-untyped-def]
        def fc(kind: str):  # type: ignore[no-untyped-def]
            r = par.add_run()
            r.font.size = Pt(size)
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
            r._r.append(e)
            return r

        fc("begin")
        r = par.add_run()
        r.font.size = Pt(size)
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = f" {instr} "
        r._r.append(it)
        fc("separate")
        par.add_run(cached).font.size = Pt(size)
        fc("end")

    # ---- headings
    def heading(
        self, text: str, level: int, number: bool = True, page_break: bool | None = None
    ) -> None:
        label = text
        if level <= 2 and number:
            if level == 1:
                self.counters = [self.counters[0] + 1, 0]
                label = f"{self.counters[0]}  {text}"
            else:
                self.counters[1] += 1
                label = f"{self.counters[0]}.{self.counters[1]}  {text}"
        if page_break if page_break is not None else level == 1:
            self.doc.add_page_break()
        self.doc.add_heading(label, level=level)
        if level <= 2:
            self.toc.append((level, label))

    def appendix(self, letter: str, text: str) -> None:
        self.doc.add_page_break()
        label = f"Appendix {letter}  {text}"
        self.doc.add_heading(label, level=1)
        self.toc.append((1, label))
        self.counters = [0, 0]

    # ---- text
    def para(
        self,
        text: str,
        style: str | None = None,
        size: float | None = None,
        align=None,
        italic: bool = False,
    ):  # type: ignore[no-untyped-def]
        p = self.doc.add_paragraph(style=style)
        self.inline(p, text, size, italic)
        if align is not None:
            p.alignment = align
        return p

    def inline(self, par, text: str, size: float | None = None, italic: bool = False) -> None:  # type: ignore[no-untyped-def]
        """**bold**, *italic*, `code`, [text](link) -> text."""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text).replace("\\*", "∗").replace("\\|", "|")
        for tok in re.split(r"(\*\*.+?\*\*|`[^`]+`|(?<!\*)\*[^*\s][^*]*?\*(?!\*))", text):
            if not tok:
                continue
            if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
                r = par.add_run(tok[2:-2])
                r.bold = True
            elif tok.startswith("`") and tok.endswith("`"):
                r = par.add_run(tok[1:-1])
                r.font.name = "Consolas"
                r.font.size = Pt((size or 11) - 1)
                r._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Consolas")
                continue
            elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
                r = par.add_run(tok[1:-1])
                r.italic = True
            else:
                r = par.add_run(tok)
            if size:
                r.font.size = Pt(size)
            if italic:
                r.italic = True

    def bullets(self, items: list[str], numbered: bool = False) -> None:
        for i, it in enumerate(items, 1):
            p = self.doc.add_paragraph(style=None if numbered else "List Bullet")
            p.paragraph_format.space_after = Pt(2)
            if numbered:  # own numbering: Word's "List Number" would continue across the document
                p.paragraph_format.left_indent = Cm(0.9)
                p.paragraph_format.first_line_indent = Cm(-0.6)
                p.add_run(f"{i}.  ")
            self.inline(p, it)

    def code(self, text: str, size: float = 8.5) -> None:
        for line in text.split("\n"):
            p = self.doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.left_indent = Cm(0.3)
            p.paragraph_format.keep_together = True
            ppr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "F0F2F5")
            ppr.append(shd)
            r = p.add_run(line or " ")
            r.font.name, r.font.size = "Consolas", Pt(size)
            r._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Consolas")
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- figures and tables
    def image(
        self, path: Path, caption: str, width_cm: float | None = None, max_h_cm: float = 17.0
    ) -> None:
        iw, ih = Image.open(path).size
        w = min(width_cm or TEXT_W, TEXT_W)
        if w * ih / iw > max_h_cm:
            w = max_h_cm * iw / ih
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Cm(w))
        self.images.append(path)
        self.fig += 1
        c = self.doc.add_paragraph(style="Caption")
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.add_run(f"Figure {self.fig}. {caption}")

    def table(
        self,
        rows: list[list[str]],
        caption: str,
        size: float = 9,
        widths: list[float] | None = None,
    ) -> None:
        self.tab += 1
        c = self.doc.add_paragraph(style="Caption")
        c.paragraph_format.keep_with_next = True
        c.add_run(f"Table {self.tab}. {caption}")
        t = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        total = sum(widths) if widths else len(rows[0])
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                cell = t.cell(i, j)
                cell.width = Cm(TEXT_W * (widths[j] if widths else 1) / total)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.keep_with_next = i < 2  # header never stranded at a page end
                self.inline(p, val, size)
                if i == 0:
                    for r in p.runs:
                        r.bold = True
                    tcpr = cell._tc.get_or_add_tcPr()
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:fill"), "DCE6F2")
                    tcpr.append(shd)
                elif re.fullmatch(r"[-+]?[\d.,]+%?", val):
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if rows:  # repeat the header row on every page
            trpr = t.rows[0]._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            th.set(qn("w:val"), "true")
            trpr.append(th)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- markdown
    def markdown(
        self,
        path: Path,
        base: int,
        skip_first_h1: bool = True,
        skip_h2: tuple[str, ...] = (),
        after: dict[str, Callable[[], None]] | None = None,
    ) -> None:
        """Render a repo markdown file; its `#` headings become level `base`, `##` base+1 ..."""
        skipping = False
        pending_caption = ""
        first = True
        current = ""
        after = after or {}
        for b in K.parse_md(path):
            if b.kind == "h" and b.level == 2:
                if current in after:
                    after[current]()
                current = b.text
            if b.kind == "h":
                if first and b.level == 1 and skip_first_h1:
                    first = False
                    continue
                first = False
                skipping = b.level == 2 and b.text in skip_h2
                if skipping:
                    continue
                lvl = min(3, base + b.level - 1)
                if lvl <= 2:
                    self.heading(re.sub(r"[`*]", "", b.text), lvl, number=True, page_break=False)
                else:
                    self.doc.add_heading(re.sub(r"[`*]", "", b.text), level=3)
                pending_caption = re.sub(r"[`*]", "", b.text)
                continue
            if skipping:
                continue
            first = False
            if b.kind == "p":
                self.para(b.text)
            elif b.kind == "ul":
                self.bullets(b.items or [])
            elif b.kind == "ol":
                self.bullets(b.items or [], numbered=True)
            elif b.kind == "code":
                self.code(b.text)
            elif b.kind == "img":
                self.image(b.path, b.text or path.stem, width_cm=15.0)  # type: ignore[arg-type]
            elif b.kind == "table" and b.rows:
                ncols = len(b.rows[0])
                size = 9 if ncols <= 5 else 8
                self.table(b.rows, f"{pending_caption or path.stem} ({path.name})", size=size)
        if current in after:
            after[current]()

    # ---- table of contents (static entries; Word replaces them when the field is updated)
    def build_toc(self, at) -> None:  # type: ignore[no-untyped-def]
        """Insert a TOC field before paragraph `at`. Its cached result lists the headings, so the
        TOC reads correctly even before Word updates the field (which adds page numbers)."""
        from docx.text.paragraph import Paragraph  # noqa: PLC0415

        def fld_run(kind: str = "", instr: str = ""):  # type: ignore[no-untyped-def]
            run = OxmlElement("w:r")
            if kind:
                e = OxmlElement("w:fldChar")
                e.set(qn("w:fldCharType"), kind)
            else:
                e = OxmlElement("w:instrText")
                e.set(qn("xml:space"), "preserve")
                e.text = instr
            run.append(e)
            return run

        pars = []
        for lvl, txt in self.toc:
            el = OxmlElement("w:p")
            at._p.addprevious(el)
            par = Paragraph(el, at._parent)
            par.paragraph_format.left_indent = Cm(0.8 * (lvl - 1))
            par.paragraph_format.space_after = Pt(2)
            par.add_run(txt).bold = lvl == 1
            pars.append(par)
        first, last = pars[0]._p, pars[-1]._p
        at_idx = 1 if first.pPr is not None else 0
        for k, run in enumerate(
            [fld_run("begin"), fld_run(instr=r' TOC \o "1-2" \h \z \u '), fld_run("separate")]
        ):
            first.insert(at_idx + k, run)
        last.append(fld_run("end"))


# ------------------------------------------------------------------ the report


def code_where(items: list[tuple[str, str]]) -> str:
    return "; ".join(f"`{K.code_ref(f, n)}` ({n})" for f, n in items)


ALGO_CODE = {
    "Depth-first search": [
        ("search.py", "dfs"),
        ("search.py", "flood_fill_count"),
        ("search.py", "dead_end_cells"),
        ("maze.py", "carve_dfs"),
        ("agents.py", "TomAgent.sweep"),
    ],
    "Depth-limited search": [
        ("search.py", "dls"),
        ("search.py", "dls_safe_paths"),
        ("agents.py", "evade_plan"),
        ("agents.py", "JerryAgent.evade"),
    ],
    "Bidirectional BFS": [
        ("search.py", "bidirectional_bfs"),
        ("search.py", "reachable"),
        ("maze.py", "validate"),
        ("agents.py", "TomAgent.ambush"),
    ],
    "Greedy best-first": [
        ("search.py", "greedy_best_first"),
        ("agents.py", "TomAgent.easy"),
        ("agents.py", "JerryAgent.easy"),
    ],
    "A*": [
        ("search.py", "astar"),
        ("agents.py", "TomAgent.hunt"),
        ("agents.py", "JerryAgent.run_to"),
        ("agents.py", "JerryAgent.cost_fn"),
    ],
    "Minimax": [
        ("minimax.py", "plain_minimax"),
        ("minimax.py", "alphabeta"),
        ("minimax.py", "evaluate"),
        ("minimax.py", "decide"),
        ("agents.py", "_AIAgent.minimax_plan"),
    ],
    "MCTS": [
        ("mcts.py", "mcts"),
        ("mcts.py", "opponent_cells"),
        ("agents.py", "_AIAgent.mcts_plan"),
    ],
    "Fuzzy": [
        ("fuzzy.py", "FuzzySystem"),
        ("fuzzy.py", "TomController"),
        ("fuzzy.py", "JerryController"),
        ("agents.py", "TomAgent.act"),
        ("agents.py", "JerryAgent.act"),
    ],
}
# (report section title, ALGORITHMS.md heading that starts with this, ALGO_CODE key)
ALGORITHMS = [
    ("Depth-first search (DFS)", "Depth-first search", "Depth-first search"),
    ("Depth-limited search (DLS)", "Depth-limited search", "Depth-limited search"),
    ("Bidirectional search", "Bidirectional BFS", "Bidirectional BFS"),
    ("Greedy best-first search", "Greedy best-first", "Greedy best-first"),
    ("A* search", "A*", "A*"),
    ("Minimax with alpha-beta pruning", "Minimax with alpha-beta", "Minimax"),
    ("Monte Carlo tree search (MCTS)", "MCTS", "MCTS"),
    ("Fuzzy logic (Mamdani)", "Fuzzy logic", "Fuzzy"),
]


def build() -> Report:  # noqa: PLR0915
    r = Report()
    doc = r.doc
    exp = K.experiments()
    seeds = K.demo_seeds()
    concl = K.results_conclusions()
    games = exp["E1"]["games"]

    # ---- title page
    for _ in range(5):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = t.add_run("Cheese Heist")
    run.font.size, run.bold, run.font.color.rgb = Pt(40), True, RGBColor(0x1F, 0x3A, 0x5F)
    r.para(
        "A turn-based cat-and-mouse maze game that plays with eight AI techniques",
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=16,
    )
    r.para(
        "Artificial Intelligence lab, final project report",
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=13,
    )
    doc.add_paragraph()
    r.para(
        "Depth-first search, depth-limited search, bidirectional search, greedy best-first search, A*, minimax with "
        "alpha-beta pruning, Monte Carlo tree search and Mamdani fuzzy logic, implemented in Python with Pygame.",
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=11,
        italic=True,
    )
    r.para(
        "Every table, figure and number in this report is generated from the repository (traces, results/ and "
        "docs/scenario/), so it matches the live game for the same seed.",
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=10,
    )

    # ---- TOC placeholder
    doc.add_page_break()
    h = doc.add_paragraph()
    hr = h.add_run("Table of contents")
    hr.font.size, hr.bold, hr.font.color.rgb = Pt(18), True, RGBColor(0x1F, 0x3A, 0x5F)
    toc_anchor = doc.add_paragraph()  # entries are inserted before this paragraph at the end

    # ---- 1 introduction
    r.heading("Introduction and objectives", 1)
    r.para(
        "Cheese Heist is a two-player, turn-based maze game. Jerry the mouse must collect three keys and escape "
        "through the exit; Tom the cat hunts her; Bruno the dog is a scripted bodyguard that Jerry can wake. "
        "The game is a testbed: each classic AI technique of the course does real work in it, is visible in the "
        "interface and can be explained step by step."
    )
    r.heading("Objectives", 2)
    r.bullets(
        [
            "Build a complete, playable game with Pygame only: 2D top-down, single process, shapes instead of art.",
            "Use DFS, depth-limited search, bidirectional search, greedy best-first search, A*, minimax with "
            "alpha-beta pruning, MCTS and fuzzy logic where each one is genuinely the right tool.",
            "Show the reasoning: every AI move carries its mode, algorithm, node count, time and trace.",
            "Keep the game reproducible: seeded randomness, same seed and actions give the same game.",
            "Measure the design with headless experiments and a fixed, fully traced scenario.",
        ]
    )
    r.heading("How the report is organised", 2)
    r.para(
        "Chapter 2 describes the game, chapter 3 the architecture, chapter 4 each algorithm with its pseudocode and "
        "the changes made for the game, chapter 5 one complete decision scenario with all tables and trees, "
        "chapter 6 the experiments, chapter 7 conclusions and limits. The appendices list the files, the controls "
        "and the demo seeds."
    )

    # ---- 2 game
    r.heading("Game overview, rules and mechanics", 1)
    r.heading("Overview", 2)
    r.para(
        f"The board is an odd square grid ({C.DEFAULT_SIZE}x{C.DEFAULT_SIZE} by default, {C.MIN_SIZE} to {C.MAX_SIZE} "
        f"allowed) generated from a seed. A human can play Jerry or Tom against the AI, or watch two AIs; "
        "AlgoRithm Demo shows every algorithm on the current maze.".replace(
            "AlgoRithm", "Algorithm"
        )
    )
    r.image(
        K.SCREENS / "menu.png",
        "Main menu: modes, difficulty per side, map size, seed, Bruno on/off.",
        13.0,
    )
    r.image(
        K.SCREENS / "game_panel.png",
        "Playing as Jerry against a HARD Tom: board, top bar, right panel "
        "(mode chip, algorithm, nodes, ms, fuzzy bars, belief, Bruno, events) and the path/explored overlays.",
        15.5,
    )

    def bruno_figures() -> None:
        r.image(
            K.DIAGRAMS / "bruno_fsm.png",
            "Bruno's finite-state machine (constants from config.py).",
            13.5,
        )
        r.image(
            K.SCEN / "bruno" / "strip.png",
            "A recorded replay: Bruno wakes, chases Tom and bites him; Tom skips "
            "his next three actions (docs/scenario/bruno).",
            9.5,
            max_h_cm=19,
        )

    def fog_figure() -> None:
        r.image(
            K.SCREENS / "fog_view.png",
            "Human view under fog: cells outside the 5-step vision are dimmed, the "
            "opponent and Bruno are drawn only inside it.",
            15.0,
        )

    def screens() -> None:
        r.image(
            K.SCREENS / "spectator.png",
            "Spectator mode, HARD vs HARD: Tom's vision is tinted orange, Jerry's blue.",
            15.0,
        )
        r.image(K.SCREENS / "play_as_tom.png", "Playing as Tom against an AI Jerry.", 15.0)
        r.image(
            K.SCREENS / "end_screen.png",
            "End screen: winner, reason, turns, keys, Bruno activations and bites, "
            "nodes searched by each AI.",
            15.0,
        )

    r.markdown(
        K.DOCS / "RULES.md",
        base=1,
        after={
            "Bruno the dog (finite-state machine)": bruno_figures,
            "Fog of war": fog_figure,
            "Modes": screens,
        },
    )

    # ---- 3 architecture
    r.heading("System architecture", 1)
    r.para(
        "The engine (maze, game, search, fuzzy, minimax, mcts, agents) is pure Python and never imports pygame, so "
        "tests, experiments, videos of a game and the report all run headless. Only ui.py, demo.py, main.py and "
        "record.py touch Pygame. Agents never receive the GameState: they get an Observation that "
        "make_observation builds for one role, containing only what that role may know."
    )
    r.image(
        K.DIAGRAMS / "architecture.png",
        "Module architecture: engine, Pygame layer and offline tools.",
        14.5,
    )
    r.heading("Data flow of one AI move", 2)
    r.code(
        "GameState --make_observation(role)--> Observation (fog applied)\n"
        "Observation --Agent.act--> fuzzy controller -> mode\n"
        "mode --> A* | bidirectional BFS | DFS | DLS | BFS map     (close range: minimax, NIGHTMARE: MCTS target)\n"
        "--> Decision(action, mode, algorithm, nodes, ms, fuzzy_inputs, rule_strengths, path, explored, trace)\n"
        "Decision --> ui.py panel and overlays  |  results/traces/*.json  |  scenario / slides / report"
    )
    r.heading("Difficulty levels", 2)
    r.table(
        [
            ["Level", "Tom", "Jerry"],
            [
                "EASY",
                "greedy best-first to Jerry / last seen cell, else random walk",
                "greedy best-first to nearest key, then exit",
            ],
            [
                "NORMAL",
                "fuzzy mode + A* / bidirectional BFS / DFS",
                "fuzzy mode + danger-weighted A*",
            ],
            [
                "HARD",
                "NORMAL + minimax within 4 steps + key-vanish belief update",
                "NORMAL + DLS evade + minimax within 4",
            ],
            [
                "NIGHTMARE",
                "HARD + MCTS ambush target every 5 turns",
                "HARD + MCTS next key every 5 turns",
            ],
        ],
        "Difficulty levels (agents.py).",
        size=9,
        widths=[1.6, 4.5, 4.0],
    )
    r.para(
        f"Time budgets: HARD {C.HARD_MS_BUDGET} ms, NIGHTMARE {C.NIGHTMARE_MS_BUDGET} ms per move; reproducible node and "
        f"iteration caps (minimax {C.MINIMAX_NODE_CAP} nodes, MCTS {C.MCTS_ITERATIONS} iterations) make the time only a "
        "safety net."
    )

    # ---- 4 algorithms
    r.heading("Algorithms", 1)
    r.para(
        "Each section gives the idea, how the game uses or modifies the algorithm, pseudocode, complexity and where "
        "the code lives (file:line). The text is taken from docs/ALGORITHMS.md."
    )
    sections = K.md_sections(K.DOCS / "ALGORITHMS.md")
    mode_tbl = next(k for k in sections if k.startswith("Mode to algorithm"))
    r.heading("Which algorithm serves which mode", 2)
    for b in sections[mode_tbl]:
        if b.kind == "table" and b.rows:
            r.table(
                b.rows, "Mode to algorithm mapping (agents.py).", size=8.5, widths=[2.2, 3.0, 8.0]
            )
        elif b.kind == "p":
            r.para(b.text)
    for title, key, code_key in ALGORITHMS:
        heading = next(k for k in sections if k.startswith(key))
        r.heading(title, 2)
        for b in sections[heading]:
            if b.kind == "p":
                r.para(b.text)
            elif b.kind == "ul":
                r.bullets(b.items or [])
            elif b.kind == "ol":
                r.bullets(b.items or [], numbered=True)
            elif b.kind == "code":
                r.code(b.text)
            elif b.kind == "table" and b.rows:
                r.table(b.rows, f"{title}: table from docs/ALGORITHMS.md.", size=8.5)
        r.para(f"**Where in the code.** {code_where(ALGO_CODE[code_key])}.")
    r.heading("Search benchmark", 2)
    r.table(
        K.bench_table(),
        "Search algorithms on 200 mazes (start = Jerry's start, goal = Tom's start), "
        "from scripts/bench_search.py.",
        size=9,
    )

    # ---- 5 scenario
    r.heading("Step-by-step decision analysis of one scenario", 1)
    r.para(
        "The scenario is a fixed 13x13 position at turn 18 built by scenario.py. Both agents are HARD and decide on "
        "the same snapshot. The tables and figures below are generated from the live agents; a test checks that the "
        "markdown equals what the agents compute."
    )
    r.markdown(K.SCEN / "walkthrough.md", base=2, skip_h2=("Files",))
    for fname, title in (
        ("fuzzy_tom.md", "Fuzzy logic: Tom"),
        ("fuzzy_jerry.md", "Fuzzy logic: Jerry"),
        ("astar.md", "A* heuristic calculations"),
        ("astar_vs_greedy.md", "A* versus greedy on this maze"),
        ("dls.md", "Depth-limited search: Jerry's EVADE"),
        ("minimax.md", "Minimax with alpha-beta"),
        ("mcts.md", "MCTS ambush target"),
        ("bruno/frames.md", "Bruno replay"),
    ):
        r.heading(title, 2)
        r.markdown(K.SCEN / fname, base=3)

    # ---- 6 experiments
    r.heading("Experiments and results", 1)
    r.para(
        f"All experiments run headless with fixed seeds 0..{games - 1} on {C.DEFAULT_SIZE}x{C.DEFAULT_SIZE} maps "
        "(scripts/experiments.py). The outcome of each game is recorded with its cause: exit (Jerry escapes), "
        "capture (Tom catches Jerry) or timeout (the turn limit passes); Bruno's bites are counted separately. "
        "With 100 games one win rate has a 95% interval of about plus or minus 9 points, so smaller differences are "
        "called noise."
    )
    for key in ("E1", "E2", "E3", "E4", "E5", "E6"):
        r.heading(f"{key}. {K.EXPERIMENT_TITLES[key]}", 2)
        rows = exp[key]["rows"]
        r.table(
            [K.exp_header()] + [K.exp_row(n, s) for n, s in rows],
            f"{key}: results over {exp[key]['games']} games per configuration.",
            size=7.5,
            widths=[4.2, 1.1, 1.0, 1.1, 1.1, 0.9, 1.1, 1.3, 1.1, 1.3, 1.1],
        )
        r.image(K.RESULTS / f"{key}.png", f"{key}: outcome causes per configuration.", 15.0)
        r.para(f"**Conclusion.** {concl[key]}")

    # ---- 7 conclusion
    r.heading("Conclusion and limitations", 1)
    e1 = dict(exp["E1"]["rows"])
    e5 = dict(exp["E5"]["rows"])
    r.para(
        "All eight techniques run inside the game and can be inspected in the interface, in the traces and in the "
        "algorithm demo. The results are mixed, and the honest summary is:"
    )
    r.bullets(
        [
            f"The ladder works: against NORMAL Jerry, Jerry's win rate falls from "
            f"{100 * e1['Tom EASY vs Jerry NORMAL']['jerry_win']:.0f}% (EASY Tom) to "
            f"{100 * e1['Tom HARD vs Jerry NORMAL']['jerry_win']:.0f}% (HARD Tom) (E1).",
            f"HARD's strength comes mostly from the key-vanish belief update; minimax on or off gives "
            f"{100 * e5['Tom HARD (minimax on)']['jerry_win']:.0f}% versus "
            f"{100 * e5['Tom HARD without minimax']['jerry_win']:.0f}% (E5), within noise, because a depth-4 search "
            "usually agrees with the A* chase move when both characters move at the same speed.",
            "MCTS (NIGHTMARE) equals HARD within noise in these experiments; its playouts carry little signal at 20 turns.",
            "DLS depth (3, 5, 7), A* versus greedy for the chase and the fuzzy director versus always-HUNT show differences "
            "inside the noise at 100 games (E2, E3, E4).",
            "Bruno bites only EASY Tom; NORMAL and above retreat from a guarding Bruno (rule T7), so Bruno acts as deterrence (E6).",
            f"Balance: Jerry wins {100 * e1['Tom HARD vs Jerry NORMAL']['jerry_win']:.0f}-"
            f"{100 * e1['Tom HARD vs Jerry HARD']['jerry_win']:.0f}% against HARD Tom, at the low end of the 35-60% target.",
        ]
    )
    r.heading("What would improve the system", 2)
    r.bullets(
        [
            "Stronger MCTS: smarter playout policies and a deeper tree (two levels today) so NIGHTMARE separates from HARD.",
            "Evaluation weights for minimax fitted from self-play instead of hand-set.",
            "Jerry could use hidden-information search (her belief about Tom) as Tom does.",
            "More experiments per configuration (1000 games) to resolve differences of a few points.",
            "Larger maps and more Bruno behaviours.",
        ]
    )

    # ---- appendices
    r.appendix("A", "File map")
    files = [
        ("main.py", "menu, game loop, input"),
        ("config.py", "all constants"),
        ("maze.py", "DFS maze generation, placement, validation"),
        ("game.py", "GameState, rules, observation (fog), Bruno FSM"),
        ("search.py", "A*, greedy, DFS, DLS, bidirectional, BFS, IDDFS"),
        ("fuzzy.py", "Mamdani engine and Tom/Jerry controllers"),
        ("minimax.py", "minimax and alpha-beta"),
        ("mcts.py", "information-set UCT"),
        ("agents.py", "Decision, agents, difficulties"),
        ("ui.py", "drawing, HUD, panel"),
        ("demo.py", "algorithm demo screen"),
        ("scenario.py", "fixed scenario"),
        ("scenario_report.py", "scenario markdown"),
        ("scenario_plots.py", "scenario figures"),
        ("record.py", "headless frames to mp4"),
        ("scripts/experiments.py", "experiments E1-E6"),
        ("scripts/find_demo_seeds.py", "demo-video seeds"),
        ("scripts/build_slides.py", "slides"),
        ("scripts/build_report.py", "this report"),
        ("scripts/check_consistency.py", "slides/report numbers equal results/ and docs/scenario/"),
        ("scripts/build_docs.py", "docs/VIVA.md (real line numbers) and docs/DEMO.md"),
        ("tests/", "pytest suite"),
    ]
    for f, _ in files:
        assert (K.ROOT / f).exists(), f
    r.table(
        [["File", "Role"]] + [[f"`{f}`", d] for f, d in files],
        "File map.",
        size=9,
        widths=[4.5, 11.5],
    )
    r.appendix("B", "Controls")
    r.table(
        [
            ["Key", "Action"],
            ["WASD / arrows, Space", "move, wait (human modes)"],
            ["Tab (A when watching)", "path overlay"],
            ["E", "explored-cells overlay"],
            ["F", "fuzzy panel: membership curves and rule strengths"],
            ["T", "toggle saving traces to results/traces/"],
            ["P, N", "pause, single step (AI vs AI)"],
            ["+ / -", "speed 1..16 turns per second"],
            ["F2", "algorithm demo"],
            ["Esc", "back to the menu"],
            [
                "Demo: 1..8, click, right-click, Space, +/-, R, C",
                "algorithm, start, goal, play, speed, reset, compare A* vs greedy",
            ],
        ],
        "Controls.",
        size=9,
        widths=[5, 11],
    )
    r.appendix("C", "Demo videos and seeds")
    names = {
        "bruno_saves_jerry": "a_bruno_saves_jerry.mp4",
        "minimax_chase": "b_minimax_close_chase.mp4",
        "fuzzy_switch": "c_fuzzy_mode_switch.mp4",
        "full_game": "d_full_game_hard_vs_hard.mp4",
    }
    rows = [["Video (videos/)", "Seed", "Tom vs Jerry", "Turns", "Note"]]
    for key, fn in names.items():
        v = seeds[key]
        rows.append(
            [fn, str(v["seed"]), f"{v['tom']} vs {v['jerry']}", f"{v['from']}-{v['to']}", v["note"]]
        )
    r.table(
        rows,
        "Demo videos, found by scripts/find_demo_seeds.py; recorded by record.py at 8 turns per second "
        "(the fuzzy video at 4).",
        size=8.5,
        widths=[4.2, 1.0, 2.2, 1.5, 7],
    )

    r.build_toc(toc_anchor)
    del toc_anchor
    return r


# ------------------------------------------------------------------ PDF


WORD_PS = r"""
$ErrorActionPreference = 'Stop'
# `make` on Windows hands over a stripped environment (no TEMP, APPDATA, COMSPEC, ...): restore it
foreach ($scope in 'Machine', 'User') {
  foreach ($e in [Environment]::GetEnvironmentVariables($scope).GetEnumerator()) {
    if (-not (Test-Path "env:$($e.Key)")) { Set-Item "env:$($e.Key)" $e.Value }
  }
}
if (-not $env:USERPROFILE) { $env:USERPROFILE = [Environment]::GetFolderPath('UserProfile') }
if (-not $env:APPDATA) { $env:APPDATA = [Environment]::GetFolderPath('ApplicationData') }
if (-not $env:LOCALAPPDATA) { $env:LOCALAPPDATA = [Environment]::GetFolderPath('LocalApplicationData') }
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$w = $null
try {
  $w = New-Object -ComObject Word.Application
  $w.Visible = $false
  $w.DisplayAlerts = 0
  $d = $w.Documents.Open('%DOCX%')
  $d.Repaginate()
  if ($d.TablesOfContents.Count -gt 0) { $d.TablesOfContents.Item(1).Update() }
  $d.Fields.Update() | Out-Null
  $d.Save()
  $d.SaveAs2('%PDF%', 17)
  Write-Output ('PAGES=' + $d.ComputeStatistics(2))
  $d.Close($false)
} finally {
  if ($w -ne $null) { try { $w.Quit() } catch {} }
  # kill only Word processes started by this script (never the user's own windows)
  Get-Process WINWORD -ErrorAction SilentlyContinue |
    Where-Object { $before -notcontains $_.Id } | Stop-Process -Force -ErrorAction SilentlyContinue
}
"""


def to_pdf() -> str:
    """DOCX -> PDF with soffice, else Word (COM), else a clear message. Returns a status line."""
    err = ""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(OUT_DIR), str(DOCX)],
            check=True,
            capture_output=True,
        )
        return f"PDF built with LibreOffice: {PDF}"
    if sys.platform == "win32" and shutil.which("powershell"):
        # work on private copies: a stale Word instance may still hold the real files open
        tmp_docx, tmp_pdf = OUT_DIR / f"_tmp{os.getpid()}.docx", OUT_DIR / f"_tmp{os.getpid()}.pdf"
        shutil.copyfile(DOCX, tmp_docx)
        script = WORD_PS.replace("%DOCX%", str(tmp_docx)).replace("%PDF%", str(tmp_pdf))
        for _attempt in range(2):  # Word COM is flaky: one retry after a short pause
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
            err = res.stderr or res.stdout
            if res.returncode == 0 and tmp_pdf.exists():
                break
            time.sleep(3)
        if res.returncode == 0 and tmp_pdf.exists():
            shutil.copyfile(tmp_docx, DOCX)  # same content, TOC page numbers filled in
            shutil.copyfile(tmp_pdf, PDF)
            tmp_docx.unlink(missing_ok=True)
            tmp_pdf.unlink(missing_ok=True)
            pages = re.search(r"PAGES=(\d+)", res.stdout)
            return f"PDF built with Microsoft Word: {PDF} ({pages.group(1) if pages else '?'} pages); TOC page numbers updated"
    for f in (OUT_DIR / f"_tmp{os.getpid()}.docx", OUT_DIR / f"_tmp{os.getpid()}.pdf"):
        f.unlink(missing_ok=True)
    return (
        f"PDF NOT built ({err.strip()[:300]}): neither LibreOffice (soffice) nor Microsoft Word is available; the DOCX is the deliverable. "
        "Install LibreOffice and run `make report` again."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    r = build()
    r.doc.core_properties.title = "Cheese Heist report"
    r.doc.core_properties.author = "Cheese Heist"
    r.doc.save(DOCX)
    print(f"{DOCX}: {len(r.toc)} headings, {r.fig} figures, {r.tab} tables, {len(r.images)} images")
    if not args.no_pdf:
        print(to_pdf())


if __name__ == "__main__":
    main()
