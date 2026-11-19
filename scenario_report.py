"""Writes docs/scenario/*.md and *.png from the live scenario data (scenario.py).

Nothing here is typed by hand: every number comes from the Decision traces and the
functions the agents call. Wall-clock times are left out on purpose, so two runs
give identical files. No pygame here.
"""

from __future__ import annotations

import math
from pathlib import Path

import config as C
import fuzzy
import minimax
import scenario_plots as P
from fuzzy import FuzzySystem, FuzzyVar
from game import JERRY, TOM, belief_state, from_ascii, render_ascii
from scenario import (
    BRUNO_MAP,
    HIDDEN_AGE,
    SEED,
    Scenario,
    build_bruno_scenario,
    build_scenario,
)
from search import Cell, flood_fill_count

TERM_W = {"dist": C.W_DIST, "goal": C.W_GOAL, "escape": C.W_ESCAPE,
          "bruno_near": C.W_BRUNO_NEAR, "stun": C.W_STUN, "dead_end": C.W_DEAD_END}
TERM_TEXT = {"dist": "d(Tom,Jerry)", "goal": "d(Jerry,goal)", "escape": "escape routes of Jerry",
             "bruno_near": "Bruno guards near Tom", "stun": "Tom stun turns left",
             "dead_end": "Jerry in a dead end"}


# ------------------------------------------------------------------ helpers


def table(headers: list[str], rows: list[list[object]]) -> str:
    """GitHub-flavoured markdown table."""
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out) + "\n"


def cell(c: Cell | list[int]) -> str:
    return f"({c[0]},{c[1]})"


def num(x: float, digits: int = 2) -> str:
    """Compact number: integers without decimals, else `digits` decimals."""
    if isinstance(x, str):
        return {"inf": "∞", "-inf": "−∞"}.get(x, x)
    if math.isinf(x):
        return "∞" if x > 0 else "−∞"
    return str(int(x)) if float(x).is_integer() else f"{x:.{digits}f}"


def mf_text(mf: fuzzy.MF) -> str:
    return f"{mf.kind}({', '.join(f'{p:g}' for p in mf.params)})"


# ------------------------------------------------------------------ fuzzy


def fuzzy_md(trace: dict, system: FuzzySystem, name: str, meaning: dict[str, str], sc: Scenario,
             unit: str) -> str:
    """Inputs, memberships, rule strengths, aggregation, centroid arithmetic, chosen mode."""
    out = [f"# Fuzzy logic: {name}, turn {sc.state.turn}\n",
           f"![membership curves](fuzzy_{name.lower()}.png)\n",
           "## 1. Crisp inputs\n",
           table(["input", "meaning", "value"],
                 [[v, meaning[v], num(trace["inputs"][v])] for v in system.inputs])]
    rows = []
    for v, var in system.inputs.items():
        x = min(var.hi, max(var.lo, trace["inputs"][v]))
        for s, mf in var.sets.items():
            rows.append([v, s, mf_text(mf), f"{x:g}", f"{trace['memberships'][v][s]:.2f}"])
    out += ["## 2. Fuzzification (membership of each input in each set)\n",
            table(["input", "set", "membership function", "x", "μ"], rows)]
    rows, by_out = [], {s: [] for s in system.output.sets}
    for rid, ante, o in system.rules:
        mus = [trace["memberships"][v][s] for v, s in ante]
        strength = trace["rules"][[r["id"] for r in trace["rules"]].index(rid)]["strength"]
        assert strength == min(mus)
        by_out[o].append((rid, strength))
        rows.append([rid, " AND ".join(f"{v}={s}" for v, s in ante) + f" → {o}",
                     f"min({', '.join(f'{m:.2f}' for m in mus)})", f"{strength:.2f}"])
    out += ["## 3. Rules (AND = min)\n",
            table(["rule", "if … then", "strength", "value"], rows)]
    clip = {s: max((st for _, st in rs), default=0.0) for s, rs in by_out.items()}
    out += ["## 4. Implication (clip) and aggregation (max)\n",
            table(["output set", "membership function", "rules feeding it", "clip level"],
                  [[s, mf_text(system.output.sets[s]),
                    ", ".join(f"{r}={st:.2f}" for r, st in rs) or "-", f"{clip[s]:.2f}"]
                   for s, rs in by_out.items()]),
            f"Aggregated shape: μ(x) = max over sets of min(clip level, set(x)) for x = "
            f"{int(system.output.lo)}..{int(system.output.hi)}, step 1.\n"]
    pts = [(x, mu) for x, mu in trace["aggregated"] if mu > 0]
    sum_mu = sum(mu for _, mu in pts)
    sum_xmu = sum(x * mu for x, mu in pts)
    centroid = sum_xmu / sum_mu if sum_mu else float("nan")
    assert abs(centroid - trace["centroid"]) < 1e-9
    k = 3  # point table in k side-by-side column groups, to fit one printed page
    n = math.ceil(len(pts) / k)
    rows = []
    for i in range(n):
        row: list[object] = []
        for j in range(k):
            x, mu = pts[i + j * n] if i + j * n < len(pts) else ("", "")
            row += [x, f"{mu:.3f}" if mu != "" else "", f"{x * mu:.3f}" if mu != "" else ""]
        rows.append(row)
    out += ["## 5. Centroid defuzzification\n",
            f"Points with μ > 0 ({len(pts)} of {len(trace['aggregated'])}; the rest add 0):\n",
            table(["x", "μ", "x·μ"] * k, rows),
            f"- Σ μ = {sum_mu:.4f}\n- Σ x·μ = {sum_xmu:.4f}\n"
            f"- centroid = Σ x·μ / Σ μ = {sum_xmu:.4f} / {sum_mu:.4f} = **{centroid:.2f}**\n",
            "## 6. Mode\n",
            table(["output set", f"membership at {unit} = {centroid:.2f}"],
                  [[s, f"{mu:.2f}"] for s, mu in trace["output_memberships"].items()]),
            "The mode is the set with the highest membership at the centroid (ties: the set "
            "listed first).\n",
            f"**Centroid:** {trace['centroid']:.2f}\n",
            f"**Mode:** {trace['mode']}\n"]
    return "\n".join(out)


# ------------------------------------------------------------------ A*


def astar_table(trace: dict, goal: Cell) -> str:
    rows = []
    for st in trace["steps"]:
        r, c = st["expand"]
        rows.append([st["n"], cell(st["expand"]), num(st["g"]),
                     f"{st['h']} = abs({r}−{goal[0]}) + abs({c}−{goal[1]})", num(st["f"]),
                     st["open_size"],
                     ", ".join(f"{cell(p)} f={num(f)}" for p, f in st["open_top"]) or "-"])
    return table(["n", "expand", "g", "h (Manhattan)", "f = g + h", "open size",
                  "open list, best first (top 5)"], rows)


def astar_md(sc: Scenario) -> str:
    tom_goal = sc.state.jerry
    t = sc.hunt.traces[0]
    k = sc.kennel_run.traces[0]
    kg = sc.state.maze.kennel
    return "\n".join([
        f"# A* on the scenario (turn {sc.state.turn})\n",
        "A* expands the open cell with the smallest f = g + h. g = cost paid so far, "
        "h = Manhattan distance to the goal. Ties: smaller h first, then first in, first out.\n",
        f"## 1. Tom HUNT: {cell(sc.state.tom)} → Jerry {cell(tom_goal)}\n",
        "Unit cost per cell. Fuzzy logic chose HUNT, so this is the search HUNT runs; the "
        "close-range minimax then overrides its action (see walkthrough.md).\n",
        astar_table(t, tom_goal),
        f"**Path:** {' → '.join(cell(c) for c in t['path'])}  \n"
        f"**Nodes expanded:** {t['nodes']}  \n**First step:** {sc.hunt.action}\n",
        f"## 2. Jerry RUN_FOR_BRUNO: {cell(sc.state.jerry)} → kennel {cell(kg)}\n",
        "Danger-weighted: entering a cell costs 1 + 4·risk(cell) (+3 on dead-end cells while "
        "Tom is within 8), risk = max(0, 6 − d_tom(cell)) / 6. Cells next to Tom cost "
        "almost 5, so g is no longer the step count.\n",
        astar_table(k, kg),
        f"**Path:** {' → '.join(cell(c) for c in k['path'])}  \n"
        f"**Nodes expanded:** {k['nodes']}  \n**First step:** {sc.kennel_run.action}\n"])


def compare_md(sc: Scenario) -> str:
    rows = []
    for c in sc.compare:
        a, g = c.astar, c.greedy
        rows.append([c.label, cell(c.start), cell(c.goal), a.nodes_expanded, len(a.path) - 1,
                     g.nodes_expanded, len(g.path) - 1,
                     "optimal" if len(g.path) == len(a.path) else
                     f"+{len(g.path) - len(a.path)} steps longer"])
    return "\n".join([
        "# A* versus greedy best-first (same maze, start, goal, unit cost)\n",
        "A* orders the open list by f = g + h, greedy by h alone. Greedy often expands fewer "
        "cells but it does not promise the shortest path.\n",
        table(["pair", "start", "goal", "A* nodes", "A* steps", "greedy nodes", "greedy steps",
               "greedy path"], rows)])


# ------------------------------------------------------------------ DLS


def dls_md(sc: Scenario) -> str:
    ev, s = sc.evade, sc.state
    maze = s.maze
    d_tom = maze.dist_map(s.tom)
    sp = ev.paths
    t = ev.trace
    rows = []
    for cand in t["candidates"]:
        p = [tuple(c) for c in cand["path"]]
        last = p[-1]
        flood = flood_fill_count(maze.adj, last, p)
        pen = C.EVADE_DEAD_END_PENALTY if last in maze.dead_ends else 0
        if cand["safe"]:
            assert abs(d_tom[last] + C.EVADE_FLOOD_WEIGHT * flood - pen - cand["score"]) < 1e-9
        safe_why = "yes" if cand["safe"] else "no: " + next(
            f"step {i} {cell(c)} has d_tom {d_tom.get(c)} ≤ {i}"
            for i, c in enumerate(p) if i >= 1 and d_tom.get(c, math.inf) <= i)
        rows.append([" ".join(cell(c) for c in p), safe_why, d_tom[last], flood, pen,
                     num(cand["score"]) if cand["safe"] else "-"])
    best = ev.best_path
    return "\n".join([
        f"# DLS evade, depth {C.DLS_DEPTH} (Jerry, turn {s.turn})\n",
        "Jerry's EVADE mode lists every path of exactly 5 steps (depth-limited DFS, no "
        "revisits). A path is SAFE if Jerry reaches each cell before Tom can: "
        "d_tom(cell at step t) > t. Score = d_tom(last) + 0.5·flood_fill(last) − 5 if last is "
        "a dead end. Here fuzzy logic chose RUN_FOR_BRUNO and Tom is within 4, so minimax "
        "overrides; this table shows what EVADE would do on the same position.\n",
        f"- depth limit: **{C.DLS_DEPTH}**\n- paths enumerated: **{len(sp.all_paths)}**\n"
        f"- safe paths: **{len(sp.safe)}**\n"
        f"- cutoffs (paths stopped by the depth limit, cells remained beyond): **{sp.cutoffs}**\n"
        f"- dead ends reached before the limit: **{sp.dead_ends}**\n"
        f"- Tom at {cell(s.tom)}; d_tom of Jerry's cell {cell(s.jerry)} = "
        f"{d_tom[s.jerry]}\n",
        table(["path (start .. step 5)", "safe?", "d_tom(last)", "flood fill(last)",
               "dead-end penalty", "score"], rows),
        f"**Chosen first step:** {ev.action} (best safe path {' → '.join(cell(c) for c in best)},"
        f" score {num(ev.best_score)}).\n",
        f"**Reason:** of the {len(sp.safe)} safe paths this one ends farthest from Tom "
        f"(d_tom {d_tom[best[-1]]}) with the most open space behind it. The dead-end stub never "
        f"yields a 5-step path: it ends after 2 steps ({sp.dead_ends} dead end reached).\n"])


# ------------------------------------------------------------------ minimax


def _eval_table(sc: Scenario, role: str) -> str:
    moves = sc.root[role]
    rows = []
    for term, w in TERM_W.items():
        row: list[object] = [TERM_TEXT[term], f"{w:+d}"]
        for m in moves:
            v = m.terms[term]
            row.append(f"{v} → {w * v:+d}")
        rows.append(row)
    rows.append(["**total (= minimax value)**", ""] + [f"**{num(m.value)}**" for m in moves])
    for m in moves:  # the table must add up to the search value
        assert sum(TERM_W[t] * v for t, v in m.terms.items()) == m.value
    return table(["term", "weight"] + [f"{m.action}" for m in moves], rows)


def minimax_md(sc: Scenario) -> str:
    out = [f"# Minimax with alpha-beta (turn {sc.state.turn}, depth {C.MINIMAX_DEPTH})\n",
           "Tom is MAX, Jerry is MIN, every value is from Tom's point of view. A ply is one "
           "character's move; after each Tom ply the round ends (Bruno steps, timers tick). "
           "Evaluation: E = −10·d(Tom,Jerry) + 2·d(Jerry,goal) − 3·escape − 15·bruno_near "
           "− 8·stun + 5·dead_end (weights in config.py).\n"]
    for role, who in ((TOM, "Tom"), (JERRY, "Jerry")):
        res, state = sc.minimax[role], belief_state(sc.obs[role], sc.obs[role].opp_pos)
        plain = minimax.plain_minimax(state, role)
        ab = minimax.alphabeta(state, role)
        assert plain.value == ab.value == res.value
        pv = " → ".join(f"{p.title()} {a}" for p, a, _, _ in res.pv)
        leaf = res.pv[-1]
        out += [
            f"## {who} to move\n",
            f"![{who} tree](minimax_tree{'' if role == TOM else '_jerry'}.png)\n",
            table(["", "value"],
                  [["chosen action", f"**{res.action}**"], ["root value (Tom's view)",
                                                          f"**{num(res.value)}**"],
                   ["principal variation", pv],
                   ["leaf position (Tom, Jerry)", f"{cell(leaf[2])}, {cell(leaf[3])}"],
                   ["nodes, plain minimax depth 4", plain.nodes],
                   ["nodes, alpha-beta depth 4", ab.nodes],
                   ["nodes, iterative deepening d1..d4 (what the agent runs)", res.nodes]]),
            f"### Worked evaluation of each legal {who} move\n",
            "Each column is the leaf at the end of that move's principal variation, searched "
            "with a full alpha-beta window (exact value).\n",
            _eval_table(sc, role),
            "Principal variations:\n"]
        out += [f"- {m.action}: " + " → ".join(f"{p.title()} {a}" for p, a, _, _ in m.pv)
                for m in sc.root[role]]
        out.append("")
        better = "lowest" if role == JERRY else "highest"
        out.append(f"{who} is the {'MIN' if role == JERRY else 'MAX'} player, so "
                   f"{who} takes the {better} value: **{res.action}**.\n")
        out.append(f"**Chosen:** {res.action}  \n**Value:** {num(res.value)}  \n"
                   f"**Nodes:** {res.nodes}\n")
    return "\n".join(out)


# ------------------------------------------------------------------ MCTS


def _mcts_block(res, title: str, note: str) -> list[str]:
    tr = res.trace
    n = tr["tree"][0]["visits"]
    rows = []
    for k in tr["root_children"]:
        exploit = k["win_rate"]
        explore = C.MCTS_UCB_C * math.sqrt(math.log(n) / k["visits"]) if k["visits"] else 0.0
        rows.append([cell(k["target"]), k["visits"], num(k["wins"]), f"{exploit:.3f}",
                     f"{explore:.3f}", num(k["ucb"], 3)])
    samples = tr["samples"]
    return [f"## {title}\n", note + "\n",
            f"Iterations: **{tr['iterations']}**. Chosen target (most visits): "
            f"**{cell(tr['chosen'])}**.\n",
            table(["target", "visits", "wins", "win rate = wins/visits",
                   f"explore = {C.MCTS_UCB_C}·√(ln {n} / visits)", "UCB1"], rows),
            "Sampled opponent cells (determinization, one cell per iteration):\n",
            table(["cell", "times sampled"], [[cell(c), k] for c, k in samples])]


def mcts_md(sc: Scenario) -> str:
    seen, hid = sc.mcts_seen, sc.mcts_hidden
    return "\n".join([
        f"# MCTS (information-set UCT), turn {sc.state.turn}\n",
        "MCTS is a NIGHTMARE feature: it picks Tom's ambush target. The HARD agents of this "
        "scenario do not run it, so this is what Tom's MCTS computes on the same "
        "observation, with `random.Random(" + str(SEED) + ")`. Targets: the remaining key, the "
        "kennel, Jerry's last seen cell. UCB1 = wins/visits + 1.4·√(ln N / visits).\n",
        "![MCTS](mcts_tree.png)\n",
        *_mcts_block(seen, "A. Real position: Jerry visible",
                     "Jerry is visible, so the information set is one cell and every "
                     "determinization is the same world; the tree still balances the three "
                     "targets by playouts."),
        *_mcts_block(hid, f"B. Hypothetical: Jerry unseen for {HIDDEN_AGE} turns",
                     f"Same state, but Tom last saw Jerry at {cell(sc.state.jerry)} "
                     f"{HIDDEN_AGE} turns ago. Each iteration samples a cell Jerry could have "
                     "reached by now (within 6 steps, outside Tom's vision)."),
        f"**Chosen (A):** {cell(seen.trace['chosen'])}  \n"
        f"**Chosen (B):** {cell(hid.trace['chosen'])}\n"])


# ------------------------------------------------------------------ walkthrough


def walkthrough_md(sc: Scenario) -> str:
    s = sc.state
    dt, dj = sc.decisions[TOM], sc.decisions[JERRY]
    ft = next(p for p in dt.trace["parts"] if p["type"] == "fuzzy")
    fj = next(p for p in dj.trace["parts"] if p["type"] == "fuzzy")
    rt, rj = sc.root[TOM], sc.root[JERRY]

    def moves(rs: list[minimax.RootMove]) -> str:
        return ", ".join(f"{m.action} {num(m.value)}" for m in rs)

    def top_rule(f: dict) -> str:
        r = max(f["rules"], key=lambda r: r["strength"])
        return f"{r['id']} ({r['text']}) = {r['strength']:.2f}"

    agree_t = "agrees with" if sc.hunt.action == dt.action else "differs from"
    agree_j = "agrees with" if sc.kennel_run.action == dj.action else "differs from"
    seen = sc.mcts_seen.trace
    return "\n".join([
        f"# Walkthrough: turn {s.turn}\n",
        "Both HARD agents decide on the same position (a snapshot: in a real round Jerry moves "
        "first and Tom sees the result). Everything below is generated from the live agents.\n",
        "```\n" + render_ascii(s) + "\n```\n",
        f"Jerry {cell(s.jerry)}, Tom {cell(s.tom)}, path distance "
        f"{s.maze.dist(s.jerry, s.tom)}, 2 of 3 keys taken, last key at {cell(sc.jerry_goal)}, "
        f"Bruno asleep in the kennel {cell(s.maze.kennel)} (activations left "
        f"{C.BRUNO_MAX_ACTIVATIONS - s.bruno.activations}), exit {cell(s.maze.exit)} locked. "
        f"The stub {cell((7, 5))}-{cell((8, 5))} below Jerry is a dead end; the junction "
        f"{cell((6, 1))} offers the key (north) or the kennel (south). See "
        "[maze.png](maze.png).\n",
        "![maze](maze.png)\n",
        f"## Tom (HARD): {dt.action}\n",
        f"1. **Observation.** Tom sees Jerry at path distance {int(ft['inputs']['dist'])} "
        f"(vision 5), last seen age {ft['inputs']['age']:g}, Bruno unseen "
        f"({ft['inputs']['bruno']:g}).\n"
        f"2. **Fuzzy** ([fuzzy_tom.md](fuzzy_tom.md)). Strongest rule {top_rule(ft)}. Centroid "
        f"{ft['centroid']:.2f}, mode **{ft['mode']}**.\n"
        f"3. **HUNT would run A\\*** ([astar.md](astar.md)): {sc.hunt.traces[0]['nodes']} nodes, "
        f"path of {len(sc.hunt.path) - 1} steps, first step {sc.hunt.action}.\n"
        f"4. **Close range.** Jerry is visible within {C.CLOSE_RANGE}, so minimax overrides "
        f"the mode: depth {sc.minimax[TOM].depth}, {sc.minimax[TOM].nodes} nodes "
        f"([minimax.md](minimax.md), [tree](minimax_tree.png)). Exact values: {moves(rt)}.\n"
        f"5. **Decision.** Tom plays **{dt.action}** because it has the highest value "
        f"({num(sc.minimax[TOM].value)}); it keeps the distance at "
        f"{next(m for m in rt if m.action == dt.action).terms['dist']} at the leaf, while the "
        f"other moves end farther from Jerry. The A* "
        f"step {agree_t} minimax.\n",
        f"## Jerry (HARD): {dj.action}\n",
        f"1. **Observation.** Tom is visible at distance {int(fj['inputs']['danger'])}, "
        f"{int(fj['inputs']['keys_left'])} key left, Bruno ready "
        f"({fj['inputs']['bruno_ready']:g}).\n"
        f"2. **Fuzzy** ([fuzzy_jerry.md](fuzzy_jerry.md)). Strongest rule {top_rule(fj)}. "
        f"Centroid {fj['centroid']:.2f}, mode **{fj['mode']}**.\n"
        f"3. **RUN_FOR_BRUNO would run A\\*** to the kennel: "
        f"{sc.kennel_run.traces[0]['nodes']} nodes, {len(sc.kennel_run.path) - 1} steps, first "
        f"step {sc.kennel_run.action}. (EVADE would run DLS depth {C.DLS_DEPTH}: "
        f"{len(sc.evade.paths.all_paths)} paths, {len(sc.evade.paths.safe)} safe, first step "
        f"{sc.evade.action}, [dls.md](dls.md).)\n"
        f"4. **Close range.** Tom is within {C.CLOSE_RANGE}, so minimax overrides: depth "
        f"{sc.minimax[JERRY].depth}, {sc.minimax[JERRY].nodes} nodes "
        f"([tree](minimax_tree_jerry.png)). Values from Tom's view: {moves(rj)}.\n"
        f"5. **Decision.** Jerry is MIN, so she takes the lowest value: **{dj.action}** "
        f"({num(sc.minimax[JERRY].value)}). RIGHT walks into Tom, DOWN enters the dead-end "
        f"stub, WAIT lets Tom close in. The A* step {agree_j} minimax.\n",
        "## Beyond HARD\n",
        f"NIGHTMARE Tom would also run MCTS for an ambush target ([mcts.md](mcts.md)): target "
        f"{cell(seen['chosen'])} after {seen['iterations']} iterations. "
        "A* versus greedy on this maze: [astar_vs_greedy.md](astar_vs_greedy.md).\n",
        "## Files\n",
        "maze.png, fuzzy_tom.md/png, fuzzy_jerry.md/png, astar.md, astar_vs_greedy.md, dls.md, "
        "minimax.md, minimax_tree.png, minimax_tree_jerry.png, mcts.md, mcts_tree.png, "
        "bruno/frames.md, bruno/strip.png.\n"])


# ------------------------------------------------------------------ Bruno


def bruno_md(frames: list) -> str:
    out = ["# Bruno saves Jerry\n",
           "Scripted: Jerry walks to the kennel H and waits, Tom walks toward her (BFS step). "
           "Jerry steps on H: Bruno wakes (GUARD). Tom is within 3 of Bruno, so he chases "
           "(CHASE_CAT), reaches Tom and bites: Tom is stunned for 3 turns.\n",
           "![strip](strip.png)\n"]
    for f in frames:
        out += [f"## Round {f.round}\n", "```\n" + f.ascii + "\n```\n",
                f"Jerry {cell(f.jerry)}, Tom {cell(f.tom)}, Bruno {cell(f.bruno)} "
                f"{f.bruno_state}, Tom stun {f.tom_stun}. "
                + ("Events: " + "; ".join(f.events) if f.events else "No events.") + "\n"]
    return "\n".join(out)


# ------------------------------------------------------------------ build


MEANING_TOM = {"dist": "path distance to Jerry (or her last seen cell)",
               "age": "turns since Jerry was last seen",
               "bruno": "threat of an awake Bruno: max(0, 1 − d(Bruno,Tom)/8)"}
MEANING_JERRY = {"danger": "path distance to Tom", "keys_left": "keys still on the board",
                 "bruno_ready": "1 if Bruno sleeps and has activations left"}


def build_all(out: Path) -> list[Path]:
    """Regenerate every scenario file under `out`; returns the paths written."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "bruno").mkdir(exist_ok=True)
    sc = build_scenario()
    written: list[Path] = []

    def write(name: str, text: str) -> None:
        (out / name).write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
        written.append(out / name)

    def figure(name: str) -> Path:
        written.append(out / name)
        return out / name

    P.maze_png(sc, figure("maze.png"))
    for role, key, ctl, ins, outv, meaning, unit, title in (
            (TOM, "tom", fuzzy.TomController(), fuzzy.TOM_INPUTS, fuzzy.TOM_OUTPUT, MEANING_TOM,
             "pursuit", "Tom (HARD)"),
            (JERRY, "jerry", fuzzy.JerryController(), fuzzy.JERRY_INPUTS, fuzzy.JERRY_OUTPUT,
             MEANING_JERRY, "urgency", "Jerry (HARD)")):
        trace = next(p for p in sc.decisions[role].trace["parts"] if p["type"] == "fuzzy")
        write(f"fuzzy_{key}.md", fuzzy_md(trace, ctl, key.title(), meaning, sc, unit))
        var_list: list[FuzzyVar] = list(ins)
        P.fuzzy_png(trace, var_list, outv, figure(f"fuzzy_{key}.png"),
                    f"{title}: fuzzy mode selection, turn {sc.state.turn}")
    write("astar.md", astar_md(sc))
    write("astar_vs_greedy.md", compare_md(sc))
    write("dls.md", dls_md(sc))
    write("minimax.md", minimax_md(sc))
    P.minimax_tree_png(sc.minimax[TOM].trace, figure("minimax_tree.png"),
                       "Tom's alpha-beta tree (depth 4, values from Tom's view)")
    P.minimax_tree_png(sc.minimax[JERRY].trace, figure("minimax_tree_jerry.png"),
                       "Jerry's alpha-beta tree (depth 4, values from Tom's view)")
    write("mcts.md", mcts_md(sc))
    P.mcts_png(sc, figure("mcts_tree.png"))
    write("walkthrough.md", walkthrough_md(sc))

    _, frames = build_bruno_scenario()
    start = from_ascii(BRUNO_MAP, keys_taken=2)
    (out / "bruno" / "frames.md").write_text(bruno_md(frames), encoding="utf-8", newline="\n")
    written.append(out / "bruno" / "frames.md")
    P.bruno_strip_png(start.maze, start.keys, frames, figure("bruno/strip.png"))
    return written
