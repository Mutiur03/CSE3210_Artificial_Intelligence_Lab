"""AI agents. Every agent turns an Observation into a Decision (CLAUDE.md 4.1, 4.2, 4.5).

Agents receive ONLY their Observation, never the GameState. Each keeps its own
memory (where the opponent was last seen, which cells Tom saw recently, what
Jerry believes about Bruno). Minimax and MCTS run on `game.belief_state`, a
local sub-game rebuilt from the observation plus that memory.

Difficulty (4.2):
  EASY       greedy best-first, no fuzzy logic
  NORMAL     fuzzy mode each turn -> A* / bidirectional BFS / DFS (Jerry: no DLS)
  HARD       NORMAL + minimax alpha-beta at close range (Jerry also DLS evade)
  NIGHTMARE  HARD + MCTS strategic target every 5 turns
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

import config as C
import minimax
from fuzzy import FuzzyResult, JerryController, TomController
from game import (
    JERRY,
    SLEEP,
    TOM,
    Observation,
    belief_state,
    direction,
    moves_from,
    step,
)
from maze import INF, Maze
from mcts import mcts, opponent_cells
from search import (
    Cell,
    SafePaths,
    astar,
    bfs,
    bidirectional_bfs,
    dfs,
    dls_safe_paths,
    flood_fill_count,
    greedy_best_first,
)

EASY, NORMAL, HARD, NIGHTMARE = "EASY", "NORMAL", "HARD", "NIGHTMARE"
DIFFICULTIES = (EASY, NORMAL, HARD, NIGHTMARE)
BUDGET_MS = {HARD: C.HARD_MS_BUDGET, NIGHTMARE: C.NIGHTMARE_MS_BUDGET}


@dataclass
class Decision:
    """One AI move plus everything the UI shows about how it was chosen."""

    action: str
    mode: str
    algorithm: str
    nodes: int
    ms: float
    fuzzy_inputs: dict | None = None
    rule_strengths: dict | None = None
    path: list[tuple] = field(default_factory=list)
    explored: list[tuple] = field(default_factory=list)
    trace: dict | None = None


@dataclass
class Plan:
    """What one mode handler decided (merged into the Decision)."""

    action: str
    algorithm: str
    nodes: int = 0
    path: list[Cell] = field(default_factory=list)
    explored: list[Cell] = field(default_factory=list)
    traces: list[dict] = field(default_factory=list)


class Agent(ABC):
    """Base class. Agents only ever receive Observations, never GameState."""

    name = "Agent"

    def __init__(self, seed: int, trace: bool = False) -> None:
        self.rng = random.Random(seed)
        self.trace = trace

    @abstractmethod
    def act(self, obs: Observation) -> Decision:
        """Choose this turn's action."""


class RandomAgent(Agent):
    """Picks a uniformly random legal action (seeded). Baseline for tests."""

    name = "Random"

    def act(self, obs: Observation) -> Decision:
        t0 = time.perf_counter()
        options = moves_from(obs.maze, obs.self_pos)
        action = self.rng.choice(options)
        return Decision(
            action=action, mode="SCRIPTED", algorithm="Random legal move",
            nodes=len(options), ms=(time.perf_counter() - t0) * 1000,
            path=[obs.self_pos, step(obs.self_pos, action)],
        )


# ------------------------------------------------------------------ shared helpers


def _path_plan(res_path: list[Cell], me: Cell, algorithm: str, nodes: int,
               explored: list[Cell], trace: dict | None) -> Plan:
    """Plan that takes the first step of `res_path` (WAIT if already at its end)."""
    action = direction(me, res_path[1]) if len(res_path) > 1 else "WAIT"
    return Plan(action, algorithm, nodes, res_path, explored, [trace] if trace else [])


def flee_step(maze: Maze, me: Cell, d_tom: dict[Cell, int]) -> str:
    """One-step escape: the legal move whose cell is farthest from Tom (BFS distance
    map); among equally far cells, one that is not in a dead-end corridor."""
    def key(a: str) -> tuple[int, bool]:
        cell = step(me, a)
        return d_tom.get(cell, INF), cell not in maze.dead_ends
    return max(moves_from(maze, me), key=key)


@dataclass
class EvadeResult:
    """Jerry's DLS evade analysis (also drawn by the algorithm demo)."""

    action: str
    best_path: list[Cell]
    best_score: float | None
    paths: SafePaths
    scored: list[tuple[float, list[Cell]]]
    trace: dict


def evade_plan(maze: Maze, me: Cell, tom: Cell) -> EvadeResult:
    """Jerry EVADE (HARD+): depth-limited search, depth 5 (CLAUDE.md 4.5).

    Enumerate every simple path of exactly 5 steps (search.dls_safe_paths). A
    path is SAFE if Jerry reaches each of its cells before Tom could
    (d_tom(cell) > step number). Score = d_tom(last) + 0.5 * flood_fill_count(
    last, blocked = path) - 5 if the last cell is a dead end. Take the first step
    of the best safe path; with no safe path, step to the neighbour farthest from Tom.
    """
    d_tom = maze.dist_map(tom)
    sp = dls_safe_paths(maze.adj, me, C.DLS_DEPTH, d_tom)

    def score(p: list[Cell]) -> float:
        last = p[-1]
        return (d_tom.get(last, INF) + C.EVADE_FLOOD_WEIGHT * flood_fill_count(maze.adj, last, p)
                - (C.EVADE_DEAD_END_PENALTY if last in maze.dead_ends else 0))

    scored = [(score(p), p) for p in sp.safe]
    if scored:
        best_score, best = max(scored, key=lambda sp_: sp_[0])
        action = direction(me, best[1])
    else:
        best_score, best = None, []
        action = flee_step(maze, me, d_tom)
    top = sorted(scored, key=lambda x: -x[0])[:10]
    cands = [{"path": [list(c) for c in p], "safe": True, "score": s} for s, p in top]
    unsafe = [p for p in sp.all_paths if p not in sp.safe][:10 - len(cands)]
    cands += [{"path": [list(c) for c in p], "safe": False, "score": None} for p in unsafe]
    trace = {"type": "dls", "depth_limit": C.DLS_DEPTH, "paths_enumerated": len(sp.all_paths),
             "safe_paths": len(sp.safe), "cutoffs": sp.cutoffs, "dead_ends": sp.dead_ends,
             "status": "SAFE PATH" if best else "FAIL (no safe path, flee one step)",
             "tom": list(tom), "best_path": [list(c) for c in best], "best_score": best_score,
             "candidates": cands}
    return EvadeResult(action, best, best_score, sp, scored, trace)


class _AIAgent(Agent):
    """Shared memory and Decision assembly for TomAgent and JerryAgent."""

    role = ""

    def __init__(self, difficulty: str = NORMAL, seed: int = 0, trace: bool = False) -> None:
        super().__init__(seed, trace)
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty {difficulty}")
        self.difficulty = difficulty
        self.name = f"{self.role.title()} {difficulty}"
        self.last_seen: tuple[Cell, int] | None = None  # opponent memory
        self.saw_last_turn = False
        self.newly_seen = False
        self.plan_target: Cell | None = None  # MCTS strategic choice (NIGHTMARE)
        self.plan_turn: int | None = None
        self.plan_used = -1  # last turn the planning mode was active

    def remember(self, obs: Observation) -> None:
        """Update memory from `obs` (last sighting, newly-seen flag)."""
        self.newly_seen = obs.opp_pos is not None and not self.saw_last_turn
        if obs.opp_pos is not None:
            self.last_seen = (obs.opp_pos, obs.turn)
        self.saw_last_turn = obs.opp_pos is not None

    def age(self, obs: Observation) -> int | None:
        """Turns since the opponent was last seen (None = never seen)."""
        return None if self.last_seen is None else obs.turn - self.last_seen[1]

    def budget_left(self, t0: float) -> float | None:
        budget = BUDGET_MS.get(self.difficulty)
        return None if budget is None else budget - (time.perf_counter() - t0) * 1000

    def close_range(self, obs: Observation) -> bool:
        """HARD+: opponent visible within path distance 4 -> minimax overrides the mode."""
        return (self.difficulty in (HARD, NIGHTMARE) and obs.opp_pos is not None
                and obs.maze.dist(obs.self_pos, obs.opp_pos) <= C.CLOSE_RANGE)

    def minimax_plan(self, obs: Observation, t0: float, activations: int = 0) -> Plan:
        assert obs.opp_pos is not None
        state = belief_state(obs, obs.opp_pos, activations)
        left = self.budget_left(t0)
        res = minimax.decide(state, self.role, time_limit_ms=left * 0.9 if left else None,
                             trace=self.trace)
        me = 0 if self.role == JERRY else 1
        path = [obs.self_pos] + [(cells[2], cells[3])[me] for cells in res.pv
                                 if cells[0] == self.role]
        return Plan(res.action, f"Minimax d{res.depth} alpha-beta", res.nodes, path,
                    res.explored, [res.trace] if res.trace else [])

    def mcts_plan(self, obs: Observation, targets: list[Cell], t0: float,
                  activations: int = 0) -> Plan | None:
        """NIGHTMARE: re-plan the strategic target every 5 turns, when the opponent is
        newly seen, or when the mode that uses the target was not active last turn.
        Returns the MCTS work done this turn (None if no re-plan)."""
        due = (self.plan_turn is None or obs.turn - self.plan_turn >= C.MCTS_REPLAN_TURNS
               or self.newly_seen or self.plan_used != obs.turn - 1)
        self.plan_used = obs.turn
        if self.difficulty != NIGHTMARE or not due or len(targets) < 2:
            return None
        left = self.budget_left(t0)
        res = mcts(obs, targets, opponent_cells(obs, self.last_seen), self.rng,
                   bruno_activations=activations,
                   time_limit_ms=left * 0.6 if left else None, trace=self.trace)
        self.plan_target, self.plan_turn = res.target, obs.turn
        return Plan("WAIT", f"MCTS {res.iterations} iters", res.iterations,
                    traces=[res.trace] if res.trace else [])

    def decision(self, obs: Observation, t0: float, mode: str, plan: Plan,
                 fz: FuzzyResult | None, inputs: dict | None, extra: Plan | None) -> Decision:
        """Merge mode plan (+ MCTS work) into a Decision; fills every field."""
        algorithm, nodes, traces = plan.algorithm, plan.nodes, list(plan.traces)
        if extra is not None:
            algorithm = f"{extra.algorithm} + {algorithm}"
            nodes += extra.nodes
            traces = extra.traces + traces
        ms = (time.perf_counter() - t0) * 1000
        trace = None
        if self.trace:
            trace = {"role": self.role, "turn": obs.turn, "difficulty": self.difficulty,
                     "mode": mode, "algorithm": algorithm, "action": plan.action,
                     "nodes": nodes, "ms": ms,
                     "parts": ([fz.trace] if fz is not None and fz.trace else []) + traces}
        return Decision(
            action=plan.action, mode=mode, algorithm=algorithm, nodes=nodes, ms=ms,
            fuzzy_inputs=inputs, rule_strengths=fz.rule_strengths if fz else None,
            path=list(plan.path), explored=list(plan.explored), trace=trace,
        )


# ------------------------------------------------------------------ Tom


class TomAgent(_AIAgent):
    """The cat. Modes HUNT (A*), AMBUSH (bidirectional BFS), SWEEP (DFS), RETREAT."""

    role = TOM

    def __init__(self, difficulty: str = NORMAL, seed: int = 0, trace: bool = False) -> None:
        super().__init__(difficulty, seed, trace)
        self.fuzzy = TomController()
        self.seen_at: dict[Cell, int] = {}  # cell -> last turn Tom saw it (SWEEP)
        self.known_keys: frozenset[Cell] | None = None

    def remember(self, obs: Observation) -> None:
        """Opponent memory and seen-cell map. HARD+ also infers: a key that vanished since
        Tom's last turn was just taken, so Jerry stood on that cell (public info: key
        events and remaining key cells)."""
        super().remember(obs)
        taken = (self.known_keys or obs.key_cells) - obs.key_cells
        if taken and obs.opp_pos is None and self.difficulty in (HARD, NIGHTMARE):
            self.last_seen = (min(taken), obs.turn)
            self.newly_seen = True
        self.known_keys = obs.key_cells
        for cell in obs.visible_cells:
            self.seen_at[cell] = obs.turn

    def fuzzy_inputs(self, obs: Observation) -> dict[str, float]:
        """dist to target (Jerry or her last seen cell), age of that sighting, Bruno threat."""
        maze = obs.maze
        target = obs.opp_pos or (self.last_seen[0] if self.last_seen else None)
        dist = min(30, maze.dist(obs.self_pos, target)) if target else 30
        age = self.age(obs)
        bruno = 0.0
        if obs.bruno is not None and obs.bruno[1] not in (SLEEP, "TIRED"):
            bruno = max(0.0, 1 - maze.dist(obs.bruno[0], obs.self_pos) / C.BRUNO_FEAR_RANGE)
        return {"dist": dist, "age": 40 if age is None else min(40, age), "bruno": bruno}

    def act(self, obs: Observation) -> Decision:
        t0 = time.perf_counter()
        self.remember(obs)
        if self.difficulty == EASY:
            return self.decision(obs, t0, "SCRIPTED", self.easy(obs), None, None, None)
        inputs = self.fuzzy_inputs(obs)
        fz = self.fuzzy.evaluate(inputs, trace=self.trace)
        close = self.close_range(obs)
        extra = None
        if fz.mode == "AMBUSH" and not close:  # the MCTS target is only used by AMBUSH
            extra = self.mcts_plan(obs, self.mcts_targets(obs), t0)
        if close:
            plan = self.minimax_plan(obs, t0)
        else:
            handlers: dict[str, Callable[[Observation], Plan]] = {
                "HUNT": self.hunt, "AMBUSH": self.ambush, "SWEEP": self.sweep,
                "RETREAT": self.retreat}
            plan = handlers[fz.mode](obs)
        return self.decision(obs, t0, fz.mode, plan, fz, inputs, extra)

    # ---- modes
    def easy(self, obs: Observation) -> Plan:
        """EASY: greedy best-first to Jerry if visible, else to her last seen cell, else
        a random walk."""
        target = obs.opp_pos
        if target is None and self.last_seen and self.last_seen[0] != obs.self_pos:
            target = self.last_seen[0]
        if target is None:
            action = self.rng.choice(moves_from(obs.maze, obs.self_pos))
            return Plan(action, "Random walk", 1, [obs.self_pos, step(obs.self_pos, action)])
        res = greedy_best_first(obs.maze.adj, obs.self_pos, target, trace=self.trace)
        return _path_plan(res.path, obs.self_pos, "Greedy best-first", res.nodes_expanded,
                          res.explored_order, res.trace)

    def hunt(self, obs: Observation) -> Plan:
        """HUNT: A* (unit cost, Manhattan) to Jerry, or to where she was last seen.
        Standing on that last seen cell already, there is nothing to chase: sweep."""
        target = obs.opp_pos or (self.last_seen[0] if self.last_seen else None)
        if target is None or target == obs.self_pos:
            return self.sweep(obs)
        res = astar(obs.maze.adj, obs.self_pos, target, trace=self.trace)
        return _path_plan(res.path, obs.self_pos, "A*", res.nodes_expanded,
                          res.explored_order, res.trace)

    def mcts_targets(self, obs: Observation) -> list[Cell]:
        """Strategic targets: remaining keys, open exit, kennel, Jerry's last seen cell.
        Keys come first, nearest to Jerry's last seen cell first (the HARD heuristic),
        so when playouts tell the targets apart nowhere, MCTS ties fall back to it."""
        ref = self.last_seen[0] if self.last_seen else obs.self_pos
        out = sorted(obs.key_cells, key=lambda k: (obs.maze.dist(ref, k), k))
        if obs.exit_open and obs.exit_cell is not None:
            out.append(obs.exit_cell)
        out.append(obs.kennel)
        if self.last_seen is not None:
            out.append(self.last_seen[0])
        return list(dict.fromkeys(out))

    def ambush_target(self, obs: Observation) -> Cell:
        """Open exit; else (NIGHTMARE) the MCTS target; else the key nearest Jerry's
        last seen cell (never seen: nearest to Tom)."""
        if obs.exit_open and obs.exit_cell is not None:
            return obs.exit_cell
        if self.plan_target is not None and self.plan_target in self.mcts_targets(obs):
            return self.plan_target
        ref = self.last_seen[0] if self.last_seen else obs.self_pos
        return min(sorted(obs.key_cells), key=lambda k: obs.maze.dist(ref, k))

    def ambush(self, obs: Observation) -> Plan:
        """AMBUSH: bidirectional BFS Tom <-> target gives the meeting cell and path.
        Tom walks it and stops at the last cell he reaches strictly before Jerry's
        estimated arrival (tom_dist <= jerry_est - 1), then waits there."""
        maze, me = obs.maze, obs.self_pos
        target = self.ambush_target(obs)
        res = bidirectional_bfs(maze.adj, me, target, trace=self.trace)
        path = res.path
        stop = len(path) - 1
        if self.last_seen is not None:
            jcell, seen = self.last_seen
            age = obs.turn - seen
            ahead = [i for i, c in enumerate(path) if i <= max(0, maze.dist(jcell, c) - age) - 1]
            if ahead and ahead[-1] > 0:  # an interception cell further along the path
                stop = ahead[-1]
        plan = _path_plan(path[:stop + 1], me, "Bidirectional BFS", res.nodes_expanded,
                          res.explored_order, res.trace)
        return plan

    def sweep(self, obs: Observation) -> Plan:
        """SWEEP: DFS order over the maze, rooted at Jerry's last seen cell (so cells
        near it come first); go to the first cell not seen for 20 turns (if none:
        the least recently seen) along a BFS shortest path."""
        maze, me = obs.maze, obs.self_pos
        root = self.last_seen[0] if self.last_seen else me
        order = dfs(maze.adj, root, trace=self.trace)
        stale = obs.turn - C.SWEEP_STALE_TURNS
        cands = [c for c in order.explored_order if self.seen_at.get(c, -1) < stale]
        target = cands[0] if cands else min(order.explored_order,
                                            key=lambda c: self.seen_at.get(c, -1))
        route = bfs(maze.adj, me, target)
        traces = [order.trace] if order.trace else []
        return Plan(direction(me, route.path[1]) if len(route.path) > 1 else "WAIT",
                    "DFS sweep + BFS path", order.nodes_expanded + route.nodes_expanded,
                    route.path, order.explored_order, traces)

    def retreat(self, obs: Observation) -> Plan:
        """RETREAT: one step that maximises BFS distance from Bruno."""
        bruno = obs.bruno[0] if obs.bruno is not None else obs.kennel
        d_b = obs.maze.dist_map(bruno)
        action = max(moves_from(obs.maze, obs.self_pos),
                     key=lambda a: d_b[step(obs.self_pos, a)])
        return Plan(action, "BFS distance map (flee Bruno)", len(d_b),
                    [obs.self_pos, step(obs.self_pos, action)])


# ------------------------------------------------------------------ Jerry


class JerryAgent(_AIAgent):
    """The mouse. Modes SNEAK / DASH (danger-weighted A*), EVADE (flee / DLS),
    RUN_FOR_BRUNO (A* to the kennel)."""

    role = JERRY

    def __init__(self, difficulty: str = NORMAL, seed: int = 0, trace: bool = False) -> None:
        super().__init__(difficulty, seed, trace)
        self.fuzzy = JerryController()
        self.bruno_state = SLEEP  # belief: Bruno starts asleep in the kennel
        self.activations = 0

    def remember(self, obs: Observation) -> None:
        super().remember(obs)
        if obs.bruno is not None:  # Bruno only wakes when Jerry steps on him, so she sees it
            if self.bruno_state == SLEEP and obs.bruno[1] != SLEEP:
                self.activations += 1
            self.bruno_state = obs.bruno[1]

    def tom_cell(self, obs: Observation) -> Cell | None:
        """Tom's cell if visible, else his last seen cell if at most 6 turns old."""
        if obs.opp_pos is not None:
            return obs.opp_pos
        age = self.age(obs)
        if self.last_seen is not None and age is not None and age <= C.JERRY_MEMORY_TURNS:
            return self.last_seen[0]
        return None

    def fuzzy_inputs(self, obs: Observation) -> dict[str, float]:
        tom = self.tom_cell(obs)
        danger = min(30, obs.maze.dist(obs.self_pos, tom)) if tom else 30
        ready = self.bruno_state == SLEEP and self.activations < C.BRUNO_MAX_ACTIVATIONS
        return {"danger": danger, "keys_left": len(obs.key_cells),
                "bruno_ready": 1.0 if ready else 0.0}

    def act(self, obs: Observation) -> Decision:
        t0 = time.perf_counter()
        self.remember(obs)
        if self.difficulty == EASY:
            return self.decision(obs, t0, "SCRIPTED", self.easy(obs), None, None, None)
        inputs = self.fuzzy_inputs(obs)
        fz = self.fuzzy.evaluate(inputs, trace=self.trace)
        targets = sorted(obs.key_cells, key=lambda k: (obs.maze.dist(obs.self_pos, k), k)) + (
            [obs.exit_cell] if obs.exit_open and obs.exit_cell is not None else [])
        close = self.close_range(obs)
        extra = None
        if fz.mode in ("SNEAK", "DASH") and not close:  # modes that walk to the next key
            extra = self.mcts_plan(obs, targets, t0, self.activations)
        if close:
            plan = self.minimax_plan(obs, t0, self.activations)
        elif fz.mode == "EVADE":
            plan = self.evade(obs)
        else:
            goal = obs.kennel if fz.mode == "RUN_FOR_BRUNO" else self.goal(obs)
            plan = self.run_to(obs, goal)
        return self.decision(obs, t0, fz.mode, plan, fz, inputs, extra)

    def goal(self, obs: Observation) -> Cell:
        """Next key (NIGHTMARE: the MCTS pick; else nearest by path), then the exit."""
        if not obs.key_cells:
            assert obs.exit_cell is not None  # Jerry always knows the exit
            return obs.exit_cell
        if self.plan_target is not None and self.plan_target in obs.key_cells:
            return self.plan_target
        return min(sorted(obs.key_cells), key=lambda k: obs.maze.dist(obs.self_pos, k))

    def easy(self, obs: Observation) -> Plan:
        """EASY: greedy best-first to the nearest remaining key, then the exit. No evasion."""
        res = greedy_best_first(obs.maze.adj, obs.self_pos, self.goal(obs), trace=self.trace)
        return _path_plan(res.path, obs.self_pos, "Greedy best-first", res.nodes_expanded,
                          res.explored_order, res.trace)

    def cost_fn(self, obs: Observation, tom: Cell | None) -> Callable[[Cell], float] | None:
        """Danger cost: 4 * risk(cell) with risk = max(0, 6 - d_tom(cell)) / 6, plus 3 on
        dead-end cells while Tom is within 8. None when Tom's position is unknown."""
        if tom is None:
            return None
        maze = obs.maze
        d_tom = maze.dist_map(tom)
        alert = maze.dist(obs.self_pos, tom) <= C.DEAD_END_ALERT_DIST
        dead = maze.dead_ends

        def cost(cell: Cell) -> float:
            risk = max(0, C.RISK_RADIUS - d_tom.get(cell, INF)) / C.RISK_RADIUS
            return C.RISK_WEIGHT * risk + (C.DEAD_END_COST if alert and cell in dead else 0)

        return cost

    def run_to(self, obs: Observation, goal: Cell) -> Plan:
        """SNEAK / DASH / RUN_FOR_BRUNO: danger-weighted A* to `goal`, never through
        Tom's visible cell. If Tom blocks every route, flee one step instead."""
        tom = self.tom_cell(obs)
        blocked = {obs.opp_pos} if obs.opp_pos is not None else None
        res = astar(obs.maze.adj, obs.self_pos, goal, self.cost_fn(obs, tom), blocked,
                    trace=self.trace)
        if not res.path:
            assert tom is not None  # only a visible Tom can block the way
            action = flee_step(obs.maze, obs.self_pos, obs.maze.dist_map(tom))
            return Plan(action, "A* blocked -> flee step", res.nodes_expanded,
                        [obs.self_pos, step(obs.self_pos, action)], res.explored_order)
        name = "A* (danger-weighted)" if tom is not None else "A*"
        return _path_plan(res.path, obs.self_pos, name, res.nodes_expanded,
                          res.explored_order, res.trace)

    def evade(self, obs: Observation) -> Plan:
        """EVADE: NORMAL flees one step (no DLS); HARD+ runs the depth-5 DLS evade."""
        tom = self.tom_cell(obs)
        assert tom is not None  # EVADE needs danger < Safe, i.e. a known Tom
        maze, me = obs.maze, obs.self_pos
        if self.difficulty == NORMAL:
            d_tom = maze.dist_map(tom)
            action = flee_step(maze, me, d_tom)
            return Plan(action, "BFS distance map (flee step)", len(d_tom),
                        [me, step(me, action)])
        ev = evade_plan(maze, me, tom)
        path = ev.best_path or [me, step(me, ev.action)]
        explored = list(dict.fromkeys(c for p in ev.paths.all_paths for c in p))
        return Plan(ev.action, f"DLS depth {C.DLS_DEPTH}", len(ev.paths.all_paths), path,
                    explored, [ev.trace] if self.trace else [])


def make_agent(role: str, difficulty: str, seed: int, trace: bool = False) -> _AIAgent:
    """TomAgent or JerryAgent for `role`."""
    cls = TomAgent if role == TOM else JerryAgent
    return cls(difficulty, seed, trace)
