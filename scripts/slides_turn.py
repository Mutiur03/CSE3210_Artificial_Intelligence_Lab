"""Animated slides for one full turn, both sides. Called from build_slides.build().

Covers the whole turn in order: round order, fog of war, Jerry's and Tom's decisions (observe,
fuzzy inputs, membership, rule, mode, algorithm, close-range minimax), applying the moves and
win checks, Bruno's state machine, end-of-round timers, and a recap.

Numbers: turn-18 values come from content.scenario_facts() (parsed from docs/scenario/walkthrough.md
and minimax.md). Membership values follow the CLAUDE.md 4.4 tables at the scenario inputs.
Rules: CLAUDE.md 3.2-3.7, 4.2-4.5. Animation: PowerPoint fade-in, one click per group.
"""

from __future__ import annotations

import build_slides as B
from pptx.oxml import parse_xml

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


# ------------------------------------------------------------------ animation


def _fade(ids: tuple[int, int, int], spid: int, node: str) -> str:
    """One fade-in effect (presetID 10) on shape `spid`."""
    a, b, c = ids
    tgt = f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
    return (
        f'<p:par><p:cTn id="{a}" presetID="10" presetClass="entr" presetSubtype="0" '
        f'fill="hold" grpId="0" nodeType="{node}"><p:stCondLst><p:cond delay="0"/>'
        "</p:stCondLst><p:childTnLst>"
        f'<p:set><p:cBhvr><p:cTn id="{b}" dur="1" fill="hold"><p:stCondLst>'
        '<p:cond delay="0"/></p:stCondLst></p:cTn>'
        f"{tgt}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>"
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{c}" dur="500"/>'
        f"{tgt}</p:cBhvr></p:animEffect>"
        "</p:childTnLst></p:cTn></p:par>"
    )


def reveal(slide, clicks: list[list]) -> None:  # type: ignore[no-untyped-def]
    """Fade-in on click. Each inner list is one click: its first shape is 'on click', the
    rest appear 'with previous'. Written as PowerPoint <p:timing> XML on the slide."""
    ids = iter(range(3, 1_000_000))
    seq: list[str] = []
    bld: list[str] = []
    for group in clicks:
        outer, inner = next(ids), next(ids)
        effects = []
        for k, shp in enumerate(group):
            triple = (next(ids), next(ids), next(ids))
            effects.append(_fade(triple, shp.shape_id, "clickEffect" if k == 0 else "withEffect"))
            if shp._element.tag.endswith("}sp"):  # text boxes and shapes need a build entry
                bld.append(f'<p:bldP spid="{shp.shape_id}" grpId="0" animBg="1"/>')
        seq.append(
            f'<p:par><p:cTn id="{outer}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
            f'</p:stCondLst><p:childTnLst><p:par><p:cTn id="{inner}" fill="hold"><p:stCondLst>'
            '<p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            + "".join(effects)
            + "</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"
        )
    xml = (
        f'<p:timing xmlns:p="{P_NS}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" '
        'restart="never" nodeType="tmRoot"><p:childTnLst><p:seq concurrent="1" nextAc="seek">'
        '<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
        + "".join(seq)
        + "</p:childTnLst></p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl>'
        "</p:cond></p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl>'
        "</p:cond></p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>"
        + (f"<p:bldLst>{''.join(bld)}</p:bldLst>" if bld else "")
        + "</p:timing>"
    )
    slide._element.append(parse_xml(xml))


def together(*lists: list[list]) -> list[list]:  # type: ignore[type-arg]
    """Merge click lists index by index: item i of every list appears on the same click."""
    out: list[list] = []  # type: ignore[type-arg]
    for i in range(max(len(x) for x in lists)):
        out.append([shp for x in lists if i < len(x) for shp in x[i]])
    return out


# ------------------------------------------------------------------ helpers


def row(d, s, labels: list[str], y: float, h: float, color) -> list[list]:  # type: ignore[no-untyped-def]
    """Boxes left to right joined by arrows. Click i = arrow into box i, then box i."""
    n = len(labels)
    gap = 0.45
    w = (12.2 - gap * (n - 1)) / n
    groups: list[list] = []  # type: ignore[type-arg]
    prev = None
    for i, lab in enumerate(labels):
        x = 0.55 + i * (w + gap)
        box = d.box(s, x, y, w, h, fill=B.PANEL, line=color, text=lab, size=12, color=B.TEXT)
        group = [box]
        if prev is not None:
            arr = d.arrow(s, prev + 0.03, y + h / 2, x - 0.03, y + h / 2, B.DIM)
            group.insert(0, arr)
        groups.append(group)
        prev = x + w
    return groups


def lines(d, s, items: list[str], x: float, y: float, w: float, gap: float = 0.78,
          size: int = 14) -> list[list]:  # type: ignore[type-arg]
    """One text line per click (each its own group)."""
    out = []
    for i, t in enumerate(items):
        out.append([d.text(s, "■  " + t, x, y + i * gap, w, gap, size=size)])
    return out


def card(d, s, x: float, y: float, w: float, head: str, color) -> list:  # type: ignore[no-untyped-def]
    """Coloured header bar; returned as a one-item click group."""
    return [d.box(s, x, y, w, 0.55, fill=color, line=color, text=head, size=16, bold=True,
                  color=B.PANEL)]


def note(d, s, text: str, y: float = 6.35) -> None:  # type: ignore[no-untyped-def]
    d.text(s, text, 0.55, y, 12.2, 0.6, size=13, color=B.DIM)


# ------------------------------------------------------------------ slides


def round_order(d) -> None:  # type: ignore[no-untyped-def]
    s = d.slide("One turn, start to finish: the round order")
    groups = row(
        d,
        s,
        [
            "1. Jerry acts\nobserve, decide, move,\nthen win check",
            "2. Tom acts\nskipped if stunned,\nthen win check",
            "3. Bruno steps\nscripted state machine,\nno decision",
            "4. End of round\ntimers tick,\nturn += 1",
            "5. Turn > 120?\nyes: Tom wins on time\nno: next turn",
        ],
        1.7,
        2.1,
        B.BLUE,
    )
    note(d, s, "Each side acts once per turn. Bruno is scripted. Every box below is an engine rule, "
                "not an AI choice, except the two decisions in steps 1 and 2.", 4.4)
    reveal(s, groups)


def fog(d) -> None:  # type: ignore[no-untyped-def]
    s = d.slide("Before any decision: fog of war (what each side may see)")
    jerry = [
        "Walls, kennel, and where the keys and exit are (known from the start)",
        "Tom's cell only inside vision 5 (path distance, walls block)",
        "Bruno only inside vision",
        "Tom's last seen cell and the turn she saw him (memory, ages each turn)",
    ]
    tom = [
        "Walls, kennel, and every key cell (he can smell them), keys taken",
        "Exit cell only after the 3rd key (alarm)",
        "Jerry's cell only inside vision 5, and her last seen cell and turn",
        "Bruno only inside vision",
    ]
    hj = card(d, s, 0.55, 1.4, 5.95, "Jerry knows", B.BLUE)
    ht = card(d, s, 6.8, 1.4, 5.95, "Tom knows", B.ORANGE)
    body = together(lines(d, s, jerry, 0.6, 2.2, 5.85), lines(d, s, tom, 6.85, 2.2, 5.85))
    note(d, s, "Turn 18: Tom is 3 steps from Jerry, so both see each other. Each agent gets an "
                "Observation built by make_observation(state, role), never the GameState.", 5.75)
    reveal(s, [hj, ht] + body)


def side_decision(d, s, ys: float, labels: list[str], color, result: str,
                  others: str, next_step: str) -> list[list]:  # type: ignore[no-untyped-def,type-arg]
    """Shared layout for a fuzzy decision: flow row, then result and notes, one per click."""
    groups = row(d, s, labels, ys, 2.0, color)
    text = lines(d, s, [result, others, next_step], 0.55, 4.25, 12.2, gap=0.7, size=15)
    return groups + text


def jerry_decision(d, sc: dict[str, str]) -> None:
    s = d.slide("Jerry's decision, step 1: observe and fuzzify")
    groups = side_decision(
        d,
        s,
        1.5,
        [
            "1. Observe\nTom visible,\npath distance 3",
            "2. Fuzzy inputs\ndanger = 3\nkeys_left = 1, bruno_ready = 1",
            "3. Membership\ndanger Close 1.00\nkeys Some 1.00, Bruno Yes 1.00",
            "4. Rule J3 = 1.00\ndanger Close AND\nbruno Yes -> BRUNO",
            f"5. Mode\n{sc['jerry_mode']}\ncentroid {sc['jerry_centroid']}",
        ],
        B.BLUE,
        f"Result: mode {sc['jerry_mode']} (centroid {sc['jerry_centroid']}, the BRUNO set peaks at 65)",
        "Rules J1, J2 and J4-J7 stay at 0: their inputs do not match (Safe, Medium, Bruno No, keys Done)",
        "Fuzzy picks WHAT Jerry wants this turn (go to the kennel). Close range may still override it (step 3).",
    )
    reveal(s, groups)


def tom_decision(d, sc: dict[str, str]) -> None:
    s = d.slide("Tom's decision, step 1: observe and fuzzify")
    groups = side_decision(
        d,
        s,
        1.5,
        [
            "1. Observe\nJerry visible,\npath distance 3, age 0",
            "2. Fuzzy inputs\ndist = 3, age = 0\nbruno = 0 (Bruno unseen)",
            "3. Membership\ndist Near 1.00\nage Fresh 1.00, bruno Low 1.00",
            "4. Rule T1 = 1.00\ndist Near AND age Fresh\nAND bruno Low -> HUNT",
            f"5. Mode\n{sc['tom_mode']}\ncentroid {sc['tom_centroid']}",
        ],
        B.ORANGE,
        f"Result: mode {sc['tom_mode']} (centroid {sc['tom_centroid']})",
        "Rules T2-T7 stay at 0: Mid, Far, Stale, Lost and Bruno High do not match this position",
        "Fuzzy picks WHAT Tom wants this turn (hunt Jerry). Close range may still override it (step 3).",
    )
    reveal(s, groups)


def mode_algorithm_cards(d, sc: dict[str, str]) -> None:
    s = d.slide("From mode to a first step (before close range)")
    hj = card(d, s, 0.55, 1.4, 5.95, f"Jerry: {sc['jerry_mode']}", B.BLUE)
    ht = card(d, s, 6.8, 1.4, 5.95, f"Tom: {sc['tom_mode']}", B.ORANGE)
    body = together(
        lines(
            d,
            s,
            [
                "Algorithm: A* to the kennel, danger-weighted (cells near Tom cost more)",
                "Result: 7 nodes expanded, 6-step path, first step LEFT",
                "EVADE would instead run DLS depth 5: 3 paths, 2 safe, first step LEFT",
            ],
            0.6,
            2.2,
            5.85,
            gap=0.95,
        ),
        lines(
            d,
            s,
            [
                "Algorithm: A* to Jerry's cell, Manhattan heuristic, 1 per cell",
                "Result: 4 nodes expanded, 3-step path, first step LEFT",
                "Both sides' first step is LEFT. Minimax on the next slide checks it.",
            ],
            6.85,
            2.2,
            5.85,
            gap=0.95,
        ),
    )
    note(d, s, "These are the plans the modes would run. Close range overrides the mode's move "
                "when the other side is near (next slide).", 5.6)
    reveal(s, [hj, ht] + body)


def mode_table(d) -> None:
    s = d.slide("Every mode runs one algorithm")
    d.table(
        s,
        [
            ["Role", "Mode", "Algorithm that runs", "Why"],
            ["Tom", "HUNT", "A* to Jerry (or her last seen cell)", "Shortest route to a target he can chase"],
            ["Tom", "AMBUSH", "Bidirectional BFS to the target, then wait", "Meeting cell found from both ends"],
            ["Tom", "SWEEP", "DFS over cells not seen for 20 turns", "Systematic search of unseen rooms"],
            ["Tom", "RETREAT", "One step that maximises distance from Bruno", "Get out of a guard dog's reach"],
            ["Jerry", "SNEAK", "A* to the next key, danger-weighted", "Cheap route that avoids Tom's area"],
            ["Jerry", "EVADE", "DLS depth 5, safe paths (HARD+); flee within 2 (NORMAL)", "Escape path Tom cannot cut off"],
            ["Jerry", "RUN_FOR_BRUNO", "A* to the kennel, danger-weighted", "Wake Bruno so he chases Tom"],
            ["Jerry", "DASH", "A* to the exit, danger-weighted", "Exit is open: shortest safe run"],
        ],
        0.55,
        1.4,
        12.2,
        col_w=[1.2, 2.0, 4.9, 4.1],
        size=13,
        row_h=0.5,
        bold_first_col=True,
        align_right_from=9,
    )
    d.text(s, "AMBUSH and SNEAK/DASH targets come from MCTS on NIGHTMARE only (every 5 turns or on a new sighting).",
           0.55, 6.1, 12.2, 0.5, size=13, color=B.DIM)


def level_table(d) -> None:
    s = d.slide("Which algorithms run at each level")
    d.table(
        s,
        [
            ["Level", "Tom", "Jerry"],
            ["EASY", "Greedy best-first to Jerry if visible, else last seen, else random walk. No fuzzy.",
             "IDDFS to the nearest key, then the exit. No evasion."],
            ["NORMAL", "Fuzzy mode, then A* / bidirectional BFS / DFS",
             "Fuzzy mode, then danger-weighted A*. One-step flee when Tom is within 2."],
            ["HARD", "NORMAL, plus minimax alpha-beta when Jerry is within 4, plus vanished-key belief",
             "NORMAL, plus DLS evade (depth 5), plus minimax when Tom is within 4"],
            ["NIGHTMARE", "HARD, plus MCTS picks the ambush target every 5 turns",
             "HARD, plus MCTS picks the next key every 5 turns"],
        ],
        0.55,
        1.4,
        12.2,
        col_w=[1.7, 5.25, 5.25],
        size=14,
        row_h=0.95,
        bold_first_col=True,
        align_right_from=9,
    )


def close_range(d, sc: dict[str, str]) -> None:
    s = d.slide("Close range: minimax overrides the mode")
    d.text(s, "Trigger: the other side is visible within path distance 4 (HARD and above). Minimax then "
               "picks the move, and the mode's move is dropped.", 0.55, 1.25, 12.2, 0.6, size=15)
    ht = card(d, s, 0.55, 2.0, 5.95, f"Tom: depth 4 alpha-beta, {sc['tom_mm_nodes']} nodes", B.ORANGE)
    hj = card(d, s, 6.8, 2.0, 5.95, f"Jerry: depth 4 alpha-beta, {sc['jerry_mm_nodes']} nodes", B.BLUE)
    body = together(
        lines(
            d,
            s,
            [
                f"Values (Tom's view): {sc['tom_values']}",
                "Chosen: LEFT, the highest value (Tom is MAX)",
                "LEFT keeps Jerry at distance 3 at the leaf; the other moves end farther away",
            ],
            0.6,
            2.8,
            5.85,
            gap=0.95,
        ),
        lines(
            d,
            s,
            [
                f"Values (Tom's view): {sc['jerry_values']}",
                "Chosen: LEFT, the lowest value (Jerry is MIN)",
                "RIGHT walks into Tom, DOWN enters the dead-end stub, WAIT lets Tom close in",
            ],
            6.85,
            2.8,
            5.85,
            gap=0.95,
        ),
    )
    note(d, s, "Both chosen moves are LEFT, the same step A* gives. Full trees: minimax slides below.", 5.9)
    reveal(s, [ht, hj] + body)


def snapshot(d) -> None:
    s = d.slide("Decisions in a real round: one after the other")
    hl = card(d, s, 0.55, 1.4, 5.95, "What the scenario shows", B.GOLD)
    hr = card(d, s, 6.8, 1.4, 5.95, "What a real round does", B.GREEN)
    left = lines(
        d,
        s,
        [
            "Both HARD agents decide on the same position (turn 18)",
            "That lets the two decisions be compared side by side",
            "The game is sequential: Tom decides after Jerry's move is applied, and sees its result",
        ],
        0.6,
        2.2,
        5.85,
        gap=0.95,
    )
    right = lines(
        d,
        s,
        [
            "Jerry decides on the position she sees, then her move is applied",
            "Win checks run (exit, key, capture)",
            "Tom's observation is rebuilt from the new position",
            "Tom decides on what he now sees, then his move is applied",
            "Win checks run again",
        ],
        6.85,
        2.2,
        5.85,
        gap=0.78,
    )
    reveal(s, [hl, hr] + together(left, right))


def resolve(d) -> None:
    s = d.slide("Applying each move: win checks, in order")
    hj = card(d, s, 0.55, 1.4, 5.95, "After Jerry's move", B.BLUE)
    ht = card(d, s, 6.8, 1.4, 5.95, "After Tom's move", B.ORANGE)
    left = [
        "On the open exit: Jerry wins, even if Tom stands there (checked before capture)",
        "On a key: collected; the 3rd key opens the exit and tells Tom where it is",
        "On a locked exit: nothing happens",
        "On Tom's cell: captured, Tom wins (a capture beats a key on that cell)",
    ]
    right = [
        "On Jerry's cell (whoever moved): captured, Tom wins",
        "Stunned: his action is skipped and the stun counts down (stun 3 = 3 skipped actions)",
        "Bruno never blocks either side; cells may overlap",
    ]
    reveal(
        s,
        [hj, ht]
        + together(
            lines(d, s, left, 0.6, 2.2, 5.85, gap=0.95),
            lines(d, s, right, 6.85, 2.2, 5.85, gap=0.95),
        ),
    )


def bruno_step(d, sc: dict[str, str]) -> None:  # noqa: ARG001
    s = d.slide("Bruno's step: a scripted state machine")
    w, h = 3.2, 1.0
    sleep = d.box(s, 0.55, 1.5, w, h, fill=B.PANEL, line=B.GOLD, text="SLEEP\non the kennel",
                  size=15, color=B.TEXT, bold=True)
    guard = d.box(s, 5.05, 1.5, w, h, fill=B.PANEL, line=B.BLUE, text="GUARD\nfollows Jerry",
                  size=15, color=B.TEXT, bold=True)
    chase = d.box(s, 9.55, 1.5, w, h, fill=B.PANEL, line=B.ORANGE, text="CHASE_CAT\nhunts Tom",
                  size=15, color=B.TEXT, bold=True)
    tired = d.box(s, 5.05, 3.85, w, h, fill=B.PANEL, line=B.DIM, text="TIRED\nwalks back to kennel",
                  size=15, color=B.TEXT, bold=True)
    a1 = d.arrow(s, 3.8, 2.0, 5.0, 2.0, B.DIM, "Jerry steps on kennel", 0, -0.62, 1.8)
    a2 = d.arrow(s, 8.3, 1.95, 9.5, 1.95, B.DIM, "Tom within 3", 0, -0.45, 1.5)
    a3 = d.arrow(s, 9.5, 2.35, 8.3, 2.35, B.DIM, "bite, or Tom > 5 away", 0, 0.5, 1.9)
    a4 = d.arrow(s, 6.65, 2.5, 6.65, 3.85, B.DIM, "guard timer 0", 0.9, 0, 1.4)
    a5 = d.arrow(s, 5.05, 4.35, 3.6, 2.4, B.DIM, "tired timer 0 and on kennel", -1.0, 0.9, 2.4)
    d.text(s, "This turn (turn 18): Bruno sleeps on the kennel with 2 activations left. Jerry is not on "
               "the kennel, so nothing wakes him.", 0.55, 5.1, 12.2, 0.5, size=15, color=B.TEXT)
    groups = [
        [a1, sleep],
        [guard],
        [a2, chase],
        [a3],
        [a4, tired],
        [a5],
    ]
    rules = lines(
        d,
        s,
        [
            "GUARD: steps toward Jerry while she is more than 2 away; Tom within 3 and not stunned starts a chase",
            "CHASE_CAT: bite when Tom is within 1 and the bite cooldown is 0: Tom stunned 3 actions, cooldown 4",
            "Woken by Jerry (fewer than 2 activations): guard timer 12. Guard timer 0 means TIRED, tired timer 20",
        ],
        0.55,
        5.6,
        12.2,
        gap=0.45,
        size=12,
    )
    reveal(s, groups + rules)


def end_of_round(d) -> None:
    s = d.slide("End of round: what ticks, then the next turn")
    items = [
        "Bruno: bite cooldown -1 (not below 0); guard timer -1 in GUARD or CHASE_CAT; tired timer -1 in TIRED",
        "Tom's stun does not tick here: it ticks each time his action is skipped",
        "turn += 1. Each side's 'age' of the other's last sighting grows by itself (age = turn - turn seen)",
        "turn > 120: Tom wins on time",
        "A win ends the turn at once: no Bruno step, no timers, no turn increment",
    ]
    reveal(s, lines(d, s, items, 0.6, 1.6, 12.1, gap=0.95, size=16))


def recap(d) -> None:
    s = d.slide("The whole turn on one page")
    left = [
        "1. Engine builds Jerry's observation (fog applied)",
        "2. Jerry: fuzzy inputs, rules, centroid, mode",
        "3. Jerry: the mode's algorithm gives a step; close range: minimax",
        "4. Jerry's move is applied; win checks (exit, key, capture)",
        "5. Engine builds Tom's observation from the new position",
    ]
    right = [
        "6. Tom: fuzzy inputs, rules, centroid, mode",
        "7. Tom: the mode's algorithm gives a step; close range: minimax",
        "8. Tom's move is applied (skipped if stunned); win checks",
        "9. Bruno's state machine steps",
        "10. End of round: timers tick, turn += 1; turn > 120 means Tom wins",
    ]
    reveal(s, together(lines(d, s, left, 0.6, 1.5, 5.9, gap=0.82, size=15),
                       lines(d, s, right, 6.85, 1.5, 5.9, gap=0.82, size=15)))
    note(d, s, "Difficulty changes only steps 2-3 and 6-7: EASY has no fuzzy logic; NORMAL has no minimax; "
                "NIGHTMARE adds MCTS targets. Same observation and seed always give the same move.", 6.1)


def turn_chapter(d, sc: dict[str, str]) -> None:
    """Insert the full-turn chapter. Restores the chapter colour afterwards."""
    saved = d.section
    d.section = ("One full turn, both sides", B.BLUE)
    round_order(d)
    fog(d)
    jerry_decision(d, sc)
    tom_decision(d, sc)
    mode_algorithm_cards(d, sc)
    mode_table(d)
    level_table(d)
    close_range(d, sc)
    snapshot(d)
    resolve(d)
    bruno_step(d, sc)
    end_of_round(d)
    recap(d)
    d.section = saved
