"""Check that the slides and the report show the numbers and images of the real data.

Compares slides/cheese_heist.pptx and report/cheese_heist_report.docx (and docs/RESULTS.md,
docs/DEMO.md) with results/experiments.json, results/demo_seeds.json and docs/scenario/*.md,
verifies every embedded image is a byte-identical repo file, looks for empty sections, and checks
the videos. Exit code 1 if anything fails.

Usage: python scripts/check_consistency.py [--outline]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from docx import Document
from pptx import Presentation
from pptx.util import Pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402

PPTX =ROOT / "slides" / "cheese_heist.pptx"
DOCX = ROOT / "report" / "cheese_heist_report.docx"
VIDEOS = [
    "a_bruno_saves_jerry",
    "b_minimax_close_chase",
    "c_fuzzy_mode_switch",
    "d_full_game_hard_vs_hard",
]

failures: list[str] = []
checks = 0


def check(ok: bool, msg: str) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append(msg)


def sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


# ------------------------------------------------------------------ readers


def pptx_content() -> tuple[list[dict], str]:
    prs = Presentation(PPTX)
    slides = []
    for i, s in enumerate(prs.slides, 1):
        texts, tables, pics = [], [], []
        title, best = "", 0.0
        for sh in s.shapes:
            if sh.shape_type == 13:  # picture
                pics.append(sha(sh.image.blob))
            if sh.has_text_frame and sh.text_frame.text.strip():
                texts.append(sh.text_frame.text)
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size and r.font.size > Pt(best) and r.text.strip():
                            best, title = r.font.size.pt, sh.text_frame.text.split("\n")[0]
            if getattr(sh, "has_table", False) and sh.has_table:
                rows = [[c.text for c in row.cells] for row in sh.table.rows]
                tables.append(rows)
                texts += [c for r in rows for c in r]
        slides.append(
            {"n": i, "title": title, "text": "\n".join(texts), "tables": tables, "pics": pics}
        )
    return slides, "\n".join(s["text"] for s in slides)


def docx_content() -> dict:
    doc = Document(DOCX)
    body = doc.element.body
    paras, tables, heads, pics = [], [], [], []
    from docx.table import Table  # noqa: PLC0415
    from docx.text.paragraph import Paragraph  # noqa: PLC0415

    seq: list[tuple[str, str]] = []  # ("h1"/"h2"/"p"/"t", text)
    for el in body.iterchildren():
        if el.tag.endswith("}p"):
            p = Paragraph(el, doc)
            style = p.style.name if p.style is not None else ""
            if style.startswith("Heading"):
                lvl = int(style.split()[-1])
                heads.append((lvl, p.text))
                seq.append((f"h{lvl}", p.text))
            elif p.text.strip() or el.findall(".//{*}drawing"):
                paras.append(p.text)
                seq.append(("p", p.text))
        elif el.tag.endswith("}tbl"):
            t = Table(el, doc)
            rows = [[c.text for c in r.cells] for r in t.rows]
            tables.append(rows)
            seq.append(("t", ""))
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            pics.append(sha(rel.target_part.blob))
    text = "\n".join(paras + [c for t in tables for r in t for c in r])
    return {
        "paras": paras,
        "tables": tables,
        "heads": heads,
        "pics": pics,
        "text": text,
        "seq": seq,
    }


# ------------------------------------------------------------------ expected values (independent of the builders)


def fmt_row(name: str, s: dict) -> list[str]:
    c = s["causes"]
    return [
        name,
        f"{round(100 * s['jerry_win'])}",
        f"{round(100 * s['tom_win'])}",
        f"{s['avg_turns']:.1f}",
        str(c["capture"]),
        str(c["exit"]),
        str(c["timeout"]),
        f"{s['TOM']['avg_nodes']:.1f}",
        f"{s['TOM']['avg_ms']:.2f}",
        f"{s['JERRY']['avg_nodes']:.1f}",
        f"{s['JERRY']['avg_ms']:.2f}",
    ]


def md_tables(path: Path) -> list[list[list[str]]]:
    out, cur = [], []
    for ln in path.read_text(encoding="utf-8").split("\n"):
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                cur.append(cells)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def scenario_tokens() -> dict[str, list[str]]:
    """Numbers that must appear in slides and report, read from docs/scenario/*.md by regex."""
    sc = ROOT / "docs" / "scenario"
    walk = (sc / "walkthrough.md").read_text(encoding="utf-8")
    mm = (sc / "minimax.md").read_text(encoding="utf-8")
    toks = {
        "Tom fuzzy centroid": re.findall(r"Centroid ([\d.]+)", walk)[:1],
        "Jerry fuzzy centroid": re.findall(r"Centroid ([\d.]+)", walk)[1:2],
        "Tom minimax values": re.findall(r"Exact values: ([^.]*?)\.\s", walk),
        "Jerry minimax values": re.findall(r"Values from Tom's view: ([^.]*?)\.\s", walk),
        "minimax nodes": re.findall(r"depth 4, (\d+) nodes", walk),
        "plain vs alpha-beta nodes": re.findall(
            r"nodes, (?:plain minimax|alpha-beta) depth 4 \| (\d+)", mm
        ),
        "root value": re.findall(r"root value \(Tom's view\) \| \*\*(-?\d+)\*\*", mm),
    }
    return toks


# ------------------------------------------------------------------ checks


def check_experiments(exp: dict, doc: dict) -> None:
    results_md = ROOT / "docs" / "RESULTS.md"
    md_rows = [r for t in md_tables(results_md) for r in t]
    doc_rows = [r for t in doc["tables"] for r in t]
    for key, data in exp.items():
        for name, s in data["rows"]:
            want = fmt_row(name, s)
            check(
                want in md_rows,
                f"docs/RESULTS.md {key} row differs from results/experiments.json: {name}",
            )
            check(want in doc_rows, f"report {key} row differs / missing: {name}")
    # the conclusion sentences of docs/RESULTS.md appear in the report
    text = (results_md).read_text(encoding="utf-8")
    for m in re.finditer(r"\*\*Conclusion\.\*\* (.*)", text):
        check(m.group(1).strip() in doc["text"], f"report lacks conclusion: {m.group(1)[:50]}...")


def check_scenario(slides_text: str, doc: dict) -> None:
    for label, vals in scenario_tokens().items():
        check(bool(vals), f"cannot read scenario value: {label}")
        for v in vals:
            check(v in doc["text"], f"report lacks scenario {label}: {v}")
            if label in (
                "Tom fuzzy centroid",
                "Jerry fuzzy centroid",
                "Tom minimax values",
                "Jerry minimax values",
                "minimax nodes",
                "plain vs alpha-beta nodes",
                "root value",
            ):
                if label == "plain vs alpha-beta nodes" and v not in vals[:2]:
                    continue  # slides show Tom's position only
                check(v in slides_text, f"slides lack scenario {label}: {v}")
    # every table of the scenario markdown is a table of the report, row for row
    doc_rows = {tuple(r) for t in doc["tables"] for r in t}
    for md in sorted((ROOT / "docs" / "scenario").glob("*.md")) + [
        ROOT / "docs" / "scenario" / "bruno" / "frames.md"
    ]:
        for t in md_tables(md):
            for r in t:
                plain = [re.sub(r"\*\*|`", "", c).replace("\\|", "|") for c in r]
                check(tuple(plain) in doc_rows, f"report lacks table row of {md.name}: {plain[:3]}")


def check_seeds(doc: dict) -> None:
    seeds = json.loads((ROOT / "results" / "demo_seeds.json").read_text(encoding="utf-8"))
    demo = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
    for key, v in seeds.items():
        if key == "setup":
            continue
        targets = [("docs/DEMO.md", demo)]
        if v.get("video", True):
            targets += [("report", doc["text"])]  # the slides are about algorithms, not videos
        for where, text in targets:
            check(str(v["seed"]) in text, f"{where} lacks demo seed {v['seed']} ({key})")
            check(
                f"{v['from']}-{v['to']}" in text.replace("–", "-"),
                f"{where} lacks turn window of {key}",
            )


def repo_images() -> dict[str, Path]:
    out = {}
    for d in ("docs/scenario", "docs/screens", "docs/diagrams", "results"):
        for p in (ROOT / d).rglob("*.png"):
            if "frames" not in p.parts:
                out[sha(p.read_bytes())] = p
    return out


def check_images(slides: list[dict], doc: dict) -> None:
    known = repo_images()
    for s in slides:
        for h in s["pics"]:
            check(h in known, f"slide {s['n']} has an image that is not a repo file")
    for h in doc["pics"]:
        check(h in known, "report has an image that is not a repo file")
    in_doc = {known[h] for h in doc["pics"] if h in known}
    for p in sorted((ROOT / "docs" / "scenario").rglob("*.png")):
        check(p in in_doc, f"report lacks scenario image {p.relative_to(ROOT)}")
    for p in sorted((ROOT / "results").glob("E*.png")):
        check(p in in_doc, f"report lacks chart {p.relative_to(ROOT)}")


def check_empty(slides: list[dict], doc: dict) -> None:
    for s in slides:
        check(bool(s["text"].strip() or s["pics"]), f"slide {s['n']} is empty")
        check(
            "TODO" not in s["text"] and "TBD" not in s["text"], f"slide {s['n']} has a placeholder"
        )
    seq = doc["seq"]
    for i, (kind, txt) in enumerate(seq):
        if kind.startswith("h"):
            lvl = int(kind[1:])
            nxt = seq[i + 1][0] if i + 1 < len(seq) else "end"
            deeper = nxt.startswith("h") and int(nxt[1:]) > lvl
            check(
                not (nxt.startswith("h") and not deeper) and nxt != "end",
                f"report section is empty: {txt}",
            )
    check(
        not re.search(r"\b(TODO|TBD|lorem|placeholder)\b", doc["text"], re.I),
        "report contains placeholder text",
    )


def check_videos() -> None:
    import imageio.v2 as imageio  # noqa: PLC0415

    demo = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
    for name in VIDEOS:
        p = ROOT / "videos" / f"{name}.mp4"
        check(p.exists() and p.stat().st_size > 20_000, f"video missing or tiny: {p.name}")
        check(f"{name}.mp4" in demo, f"docs/DEMO.md does not mention {name}.mp4")
        if p.exists():
            r = imageio.get_reader(str(p))
            n = r.count_frames()
            size = r.get_meta_data()["size"]
            r.close()
            check(
                n >= 10 and tuple(size) == (C.WINDOW_W, C.WINDOW_H),
                f"video {p.name}: {n} frames, size {size}",
            )
            print(
                f"  video {p.name}: {p.stat().st_size // 1024} KB, {n} frames, {size[0]}x{size[1]}"
            )


def outline(slides: list[dict], doc: dict) -> None:
    print("\nSlides (title: images / tables)")
    for s in slides:
        print(f"  {s['n']:2d}. {s['title']}: {len(s['pics'])} images, {len(s['tables'])} tables")
    print(f"  total {len(slides)} slides, {sum(len(s['pics']) for s in slides)} images")
    print("\nReport outline")
    for lvl, text in doc["heads"]:
        if lvl <= 2:
            print(f"  {'  ' * (lvl - 1)}{text}")
    print(
        f"  {len(doc['pics'])} images, {len(doc['tables'])} tables, {len(doc['paras'])} paragraphs"
    )
    pdf = ROOT / "report" / "cheese_heist_report.pdf"
    print(
        f"  PDF: {'present, ' + str(pdf.stat().st_size // 1024) + ' KB' if pdf.exists() else 'not built'}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outline", action="store_true")
    args = ap.parse_args()
    exp = json.loads((ROOT / "results" / "experiments.json").read_text(encoding="utf-8"))
    for f in (PPTX, DOCX):
        if not f.exists():
            sys.exit(f"missing {f}: run make slides / make report first")
    slides, slides_text = pptx_content()
    doc = docx_content()
    check_experiments(exp, doc)
    check_scenario(slides_text, doc)
    check_seeds(doc)
    check_images(slides, doc)
    check_empty(slides, doc)
    check_videos()
    if args.outline:
        outline(slides, doc)
    print(f"\n{checks} checks, {len(failures)} failures")
    for f in failures[:60]:
        print("  FAIL:", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
