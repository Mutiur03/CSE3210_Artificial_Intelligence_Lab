"""AI agents. Every agent turns an Observation into a Decision (CLAUDE.md 4.1, 4.2).

Two AI algorithms only (user decision, see docs/DECISIONS.md):
  MINIMAX  depth-4 alpha-beta every turn on a belief sub-game (minimax.decide)
  MCTS     information-set UCT picks a target cell (mcts.mcts); the agent walks there
Tom and Jerry never use the same one in the same game (`opposite`).
A fuzzy controller (fuzzy.py) picks the MODE each turn; the mode tunes the algorithm:
minimax evaluation factors (config.MODE_SCALE) or the MCTS candidate targets.
With config.AI_FULL_INFO both sides always see both characters.

Agents receive ONLY their Observation, never the GameState. Each keeps its own
memory (where the opponent was last seen, which guessed cells it already checked,
what Jerry believes about Bruno). Both algorithms run on `game.belief_state`, a
local sub-game rebuilt from the observation plus that memory.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field

import config as C
import minimax
from fuzzy import FuzzyResult, FuzzySystem, JerryController, TomController
from game import (
    JERRY,
    SLEEP,
    TOM,
    Observation,
    belief_state,
    direction,
    moves_from,
    step,
    toward,
)
from mcts import mcts, opponent_cells
from search import Cell, bfs

MINIMAX, MCTS = "MINIMAX", "MCTS"
ALGORITHMS = (MINIMAX, MCTS)
LABEL = {MINIMAX: "Minimax alpha-beta", MCTS: "MCTS"}
BUDGET_MS = {MINIMAX: C.MINIMAX_MS_BUDGET, MCTS: C.MCTS_MS_BUDGET}


def opposite(algo: str) -> str:
    """The other algorithm: Tom and Jerry never share one in a game."""
    return MCTS if algo == MINIMAX else MINIMAX


@dataclass
class Intercept:
    """Where Tom can meet Jerry head-on: the cell `k` steps ahead on her predicted route
    that Tom reaches strictly before she does."""

    cell: Cell
    k: int
    goal: Cell  # the key / exit she is predicted to walk to
    jerry_path: list[Cell]


@dataclass
class Decision:
    """One AI move plus everything the UI shows about how it was chosen."""

    action: str
    mode: str
    algorithm: str
    nodes: int
    ms: float
    fuzzy_inputs: dict | None = None
    fuzzy: FuzzyResult | None = None
    corner: dict[str, int] | None = None  # Jerry: room left after each move (corner check)
    path: list[tuple] = field(default_factory=list)
    explored: list[tuple] = field(default_factory=list)
    trace: dict | None = None


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


class AIAgent(Agent):
    """Tom or Jerry driven by one algorithm (MINIMAX or MCTS)."""

    def __init__(self, role: str, algo: str, seed: int = 0, trace: bool = False) -> None:
        super().__init__(seed, trace)
        if algo not in ALGORITHMS:
            raise ValueError(f"unknown algorithm {algo}")
        self.role, self.algo = role, algo
        self.name = f"{role.title()} {LABEL[algo]}"
        self.last_seen: tuple[Cell, int] | None = None
        self.checked: set[Cell] = set()  # guessed cells seen empty since the last sighting
        self.known_keys: frozenset[Cell] | None = None
        self.bruno_state = SLEEP  # Jerry's belief: Bruno starts asleep in the kennel
        self.activations = 0
        self.newly_seen = False
        self.target: Cell | None = None
        self.fuzzy: FuzzySystem = TomController() if role == TOM else JerryController()
        self.last_mode = ""
        self.history: deque[tuple[Cell, Cell | None]] = deque(maxlen=C.LOOP_WINDOW)
        self.commit_until = -1  # loop breaker active up to this turn
        self.plan: list[Cell] = []  # the loop breaker's stored route
        self.prev_cell: Cell | None = None
        self.still = 0  # turns in a row on the same cell
        self.intercepting = False  # MCTS picked the interception cell: recompute it each turn
        self.icpt: Intercept | None = None  # Tom's interception plan this turn
        self.chase = False  # MCTS picked "Jerry's last seen cell": follow her sightings
        self.plan_turn: int | None = None
        self.triggers: dict[str, bool] = {}  # MCTS re-plan conditions of the last move

    def remember(self, obs: Observation) -> None:
        """Last sighting (sight, scent pulse, or for Tom a key that just vanished: Jerry
        stood there), cells already checked, and Jerry's belief about Bruno."""
        sighting = None
        if obs.opp_pos is not None:
            sighting = (obs.opp_pos, obs.turn)
        elif obs.opp_last_seen is not None and (
                self.last_seen is None or obs.opp_last_seen[1] > self.last_seen[1]):
            sighting = obs.opp_last_seen  # scent pulse (game._scent)
        taken = (self.known_keys or obs.key_cells) - obs.key_cells
        if self.role == TOM and taken and obs.opp_pos is None:
            sighting = (min(taken), obs.turn)
        self.known_keys = obs.key_cells
        self.newly_seen = not C.AI_FULL_INFO and sighting is not None and (
            self.last_seen is None or self.last_seen[0] != sighting[0])
        if sighting is not None:
            self.last_seen = sighting
            self.checked.clear()
        self.checked |= obs.visible_cells
        if self.role == JERRY and obs.bruno is not None:
            if self.bruno_state == SLEEP and obs.bruno[1] != SLEEP:
                self.activations += 1
            self.bruno_state = obs.bruno[1]

    def guess(self, obs: Observation) -> Cell:
        """Where the opponent is assumed to stand in the minimax sub-game.

        Visible: there. Else the first unchecked cell of: last sighting, then (Tom) the
        open exit and the keys nearest that sighting, since Jerry must come to them.
        All checked: forget them and take the unseen cell farthest from me.
        """
        if obs.opp_pos is not None:
            return obs.opp_pos
        cands: list[Cell] = [self.last_seen[0]] if self.last_seen else []
        if self.role == TOM:
            ref = self.last_seen[0] if self.last_seen else obs.self_pos
            if obs.exit_open and obs.exit_cell is not None:
                cands.append(obs.exit_cell)
            cands += sorted(obs.key_cells, key=lambda k: (obs.maze.dist(ref, k), k))
        for c in cands:
            if c not in self.checked:
                return c
        self.checked = set(obs.visible_cells)
        d = obs.maze.dist_map(obs.self_pos)
        return max((c for c in sorted(obs.maze.floor) if c not in obs.visible_cells),
                   key=lambda c: d[c], default=obs.self_pos)

    def act(self, obs: Observation) -> Decision:
        t0 = time.perf_counter()
        self.remember(obs)
        self.icpt = self.intercept(obs)
        inputs = self.fuzzy_inputs(obs)
        fz = self.fuzzy.evaluate(inputs, trace=self.trace)
        pair = (obs.self_pos, obs.opp_pos)
        if self.history.count(pair) >= 2:
            if obs.turn > self.commit_until:
                self.plan = []
            self.commit_until = obs.turn + C.LOOP_COMMIT_TURNS
        self.history.append(pair)
        self.still = self.still + 1 if self.prev_cell == obs.self_pos else 0
        self.prev_cell = obs.self_pos
        if self.role == JERRY and self.still >= C.STILL_TURNS and obs.turn > self.commit_until:
            self.plan, self.commit_until = [], obs.turn + C.LOOP_COMMIT_TURNS  # hiding is losing
        if obs.turn <= self.commit_until:
            d = self.loop_break_move(obs, t0, fz)
        elif fz.mode == "RUN_FOR_BRUNO":  # wake Bruno: a plain route, whatever the algorithm
            d = self.scripted_move(obs, t0, fz.mode)
        elif self.algo == MINIMAX:
            d = self.minimax_move(obs, t0, fz)
        else:
            d = self.mcts_move(obs, t0, fz)
        self.last_mode = fz.mode
        if self.role == JERRY:
            self.corner_check(obs, d)
        d.fuzzy_inputs, d.fuzzy = inputs, fz
        if d.trace is not None and fz.trace is not None:
            d.trace["parts"] = [fz.trace, *d.trace["parts"]]
        return d

    def loop_break_move(self, obs: Observation, t0: float, fz: FuzzyResult) -> Decision:
        """Both sides stepping back and forth in parallel corridors is a stalemate that
        runs out the clock (each recomputes a shortest path that flips with the other's
        cell). Once the same (own cell, opponent cell) pair shows up a third time within
        LOOP_WINDOW turns, commit for LOOP_COMMIT_TURNS turns to ONE stored route:
        Jerry to the kennel if Bruno is ready, else to the nearest key (exit when none left);
        Tom to the key nearest Jerry, but a direct chase once she is within 2. No search; the
        corner check still guards Jerry's step. A step off the stored route re-plans it.
        """
        self.target, self.plan_turn, self.chase, self.intercepting = None, None, False, False
        maze, me = obs.maze, obs.self_pos
        if self.role == JERRY:
            ready = (obs.bruno is not None and self.bruno_state == SLEEP
                     and self.activations < C.BRUNO_MAX_ACTIVATIONS)
            default = (obs.kennel if ready else
                       min(sorted(obs.key_cells), key=lambda k: maze.dist(me, k))
                       if obs.key_cells else obs.exit_cell)
            label = ("Loop breaker: commit to the kennel" if ready
                     else "Loop breaker: commit to the nearest key")
        else:
            jerry = obs.opp_pos
            default = (min(sorted(obs.key_cells), key=lambda k: maze.dist(jerry, k))
                       if obs.key_cells and jerry is not None else jerry)
            if jerry is not None and maze.dist(me, jerry) <= 2:
                default, self.plan = jerry, []  # she is right there: chase her directly
            label = "Loop breaker: commit to her key, chase when close"
        if me in self.plan and self.plan[-1] != me:
            path = self.plan[self.plan.index(me):]  # keep the stored route
        else:
            path = bfs(maze.adj, me, default).path if default is not None else [me]
            self.plan = path
        action = direction(me, path[1]) if len(path) > 1 else "WAIT"
        return self.decision(obs, t0, fz.mode, action, label, len(path), path, [], [])

    def intercept(self, obs: Observation) -> Intercept | None:
        """Tom: cut Jerry off from the front instead of following her.

        Tom knows where she is and where she must go (keys by smell, the exit after the
        alarm), so he predicts her route: the shortest path from her to the key nearest her
        (else the open exit). She moves first, so Tom beats her to the cell `k` steps ahead
        when d(Tom, cell) < k. Take the nearest such cell with k >= 2 (k = 1 is just
        chasing; the farthest would park him on her key). None: she reaches every cell of
        the route first, or is within INTERCEPT_MIN_DIST: he just chases.
        """
        if self.role != TOM or obs.opp_pos is None:
            return None
        maze, jerry = obs.maze, obs.opp_pos
        if maze.dist(obs.self_pos, jerry) <= C.INTERCEPT_MIN_DIST:
            return None  # close enough: just press the chase
        if obs.key_cells:
            goal = min(sorted(obs.key_cells), key=lambda k: maze.dist(jerry, k))
        elif obs.exit_open and obs.exit_cell is not None:
            goal = obs.exit_cell
        else:
            return None
        path = [jerry]
        while path[-1] != goal:
            path.append(toward(maze, path[-1], goal))
        d_tom = maze.dist_map(obs.self_pos)
        for k in range(2, len(path)):
            if d_tom[path[k]] + obs.self_stun < k:
                return Intercept(path[k], k, goal, path)
        return None

    def corner_check(self, obs: Observation, d: Decision) -> None:
        """Jerry: before moving, make sure the chosen move does not get her cornered.

        Room(move) = number of cells she reaches strictly before Tom after that move
        (Tom moves next; a stunned Tom is late by his stun turns): her territory. A
        small territory = a pocket or dead end Tom can seal, i.e. a trap. If the chosen
        move leaves less than MIN_ROOM cells and another move leaves more (a move that
        Tom can reach at once has room 0), take the
        move with the most room (ties: farther from Tom). Stepping onto the open exit
        is never overridden. Only checked while Tom is within CORNER_CHECK_DIST.
        """
        maze, me, tom = obs.maze, obs.self_pos, obs.opp_pos
        if tom is None or maze.dist(me, tom) > C.CORNER_CHECK_DIST:
            return
        d_tom = maze.dist_map(tom)
        late = obs.opp_stun or 0
        d_me = {a: maze.dist_map(step(me, a)) for a in moves_from(maze, me)}
        room = {a: 0 if d_tom[step(me, a)] + late <= 1 else  # Tom reaches that cell at once
                sum(1 for x, n in dm.items() if n < d_tom[x] + late) for a, dm in d_me.items()}
        d.corner = room
        if d.action not in room or (obs.exit_open and step(me, d.action) == obs.exit_cell):
            return
        if room[d.action] >= C.MIN_ROOM or max(room.values()) <= room[d.action]:
            return
        best = max(room, key=lambda a: (room[a], d_tom[step(me, a)]))
        d.action = best
        d.algorithm += f" + corner check ({room})"
        d.path = [me, step(me, best)]
        if d.trace is not None:
            d.trace["action"], d.trace["corner_override"] = best, True

    def fuzzy_inputs(self, obs: Observation) -> dict[str, float]:
        """Crisp inputs of the fuzzy controller (CLAUDE.md 4.4). `age` is 0 while the
        opponent is visible (always, with full information)."""
        maze = obs.maze
        if self.role == TOM:
            target = obs.opp_pos or (self.last_seen[0] if self.last_seen else None)
            dist = min(30, maze.dist(obs.self_pos, target)) if target else 30
            age = 40 if self.last_seen is None else min(40, obs.turn - self.last_seen[1])
            if obs.opp_pos is not None:
                age = 0
            bruno = 0.0
            if obs.bruno is not None and obs.bruno[1] not in (SLEEP, "TIRED"):
                bruno = max(0.0, 1 - maze.dist(obs.bruno[0], obs.self_pos) / C.BRUNO_FEAR_RANGE)
            return {"dist": dist, "age": age, "bruno": bruno}
        danger = min(30, maze.dist(obs.self_pos, obs.opp_pos)) if obs.opp_pos else 30
        ready = self.bruno_state == SLEEP and self.activations < C.BRUNO_MAX_ACTIVATIONS
        return {"danger": danger, "keys_left": len(obs.key_cells),
                "bruno_ready": 1.0 if ready else 0.0}

    def left_ms(self, t0: float) -> float:
        return BUDGET_MS[self.algo] - (time.perf_counter() - t0) * 1000

    def minimax_move(self, obs: Observation, t0: float, fz: FuzzyResult) -> Decision:
        """Alpha-beta (iterative deepening to depth 4) on the belief sub-game with the
        opponent at `guess`. Value is from Tom's view: Tom maximises, Jerry minimises.
        The fuzzy mode scales the evaluation terms."""
        opp = self.guess(obs)
        state = belief_state(obs, opp, self.activations)
        dist, goal, escape, bruno = C.MODE_SCALE[fz.mode]
        aim = self.icpt.cell if self.icpt and fz.mode in ("HUNT", "AMBUSH") else None
        if aim is not None:  # meet her head-on: the interception cell pulls harder than her cell
            dist *= 0.5
        tune = minimax.Tune(dist, goal, escape, bruno, None, aim, C.W_AIM if aim else 0.0)
        res = minimax.decide(state, self.role, time_limit_ms=self.left_ms(t0) * 0.9,
                             trace=self.trace, tune=tune)
        me = 0 if self.role == JERRY else 1
        path = [obs.self_pos] + [(p[3], p[2])[me] for p in res.pv if p[0] == self.role]
        if res.trace is not None:
            res.trace["assumed_opp"] = list(opp)
            res.trace["tune"] = [dist, goal, escape, bruno]
            res.trace["goal_cell"] = None
            res.trace["aim"] = list(aim) if aim else None
            res.trace["aim_w"] = tune.aim_w
        return self.decision(obs, t0, fz.mode, res.action, f"Minimax d{res.depth} alpha-beta",
                             res.nodes, path, res.explored, [res.trace] if res.trace else [])

    def mcts_targets(self, obs: Observation, mode: str = "") -> list[Cell]:
        """Candidate targets in heuristic order (MCTS ties fall back to the first).
        Tom: open exit, keys nearest Jerry's last sighting, kennel, that sighting; modes HUNT
        and AMBUSH put the interception cell first (if there is one); HUNT then Jerry's cell,
        AMBUSH / SWEEP leave it out (cut her off, do not follow).
        Jerry: keys nearest her first, then the open exit."""
        maze = obs.maze
        if self.role == JERRY:
            tom = obs.opp_pos  # keys Tom reaches first come last: they are his ambush spots
            out = sorted(obs.key_cells, key=lambda k: (
                tom is not None and maze.dist(tom, k) <= maze.dist(obs.self_pos, k),
                maze.dist(obs.self_pos, k), k))
            if obs.exit_open and obs.exit_cell is not None:
                out.append(obs.exit_cell)
            return out
        ref = self.last_seen[0] if self.last_seen else obs.self_pos
        out = [obs.exit_cell] if obs.exit_open and obs.exit_cell is not None else []
        out += sorted(obs.key_cells, key=lambda k: (maze.dist(ref, k), k))
        out.append(obs.kennel)
        if self.last_seen is not None and mode in ("", "HUNT"):
            out.insert(0, self.last_seen[0]) if mode == "HUNT" else out.append(self.last_seen[0])
        if self.icpt is not None and mode in ("HUNT", "AMBUSH"):
            out.insert(0, self.icpt.cell)
        return list(dict.fromkeys(out))

    def mcts_move(self, obs: Observation, t0: float, fz: FuzzyResult) -> Decision:
        """Re-plan the target with MCTS when it is due (every 5 turns, on a new sighting,
        while the opponent is visible, or when the target is gone); then take one
        shortest-path step toward it (Jerry routes around a visible Tom). The fuzzy mode
        shapes the candidates (HUNT: Jerry's cell first, AMBUSH: not it), RUN_FOR_BRUNO
        walks straight to the kennel and RETREAT steps away from Bruno (no search)."""
        mode = fz.mode
        if mode == "RETREAT":
            return self.scripted_move(obs, t0, mode)
        targets = self.mcts_targets(obs, mode)
        if self.chase and self.last_seen is not None:
            self.target = self.last_seen[0]
        elif self.intercepting and self.icpt is not None:
            self.target = self.icpt.cell  # she moved: so does the point Tom is aiming at
        self.triggers = {
            "no plan yet": self.target is None or self.plan_turn is None,
            f"{C.MCTS_REPLAN_TURNS} turns since plan": self.plan_turn is not None
            and obs.turn - self.plan_turn >= C.MCTS_REPLAN_TURNS,
            "new sighting": self.newly_seen,
            "opponent visible": obs.opp_pos is not None and not C.AI_FULL_INFO,
            "fuzzy mode changed": mode != self.last_mode,
            "chase target reached": self.chase and self.target == obs.self_pos,
            "intercept lost": self.intercepting and self.icpt is None,
            "target gone": not self.chase and not self.intercepting and self.target is not None
            and self.target not in targets,
        }
        due = any(self.triggers.values())
        nodes, traces, algorithm = 0, [], "MCTS plan (following)"
        if due:
            opp_cells = opponent_cells(obs, self.last_seen)
            res = mcts(obs, targets, opp_cells, self.rng, bruno_activations=self.activations,
                       time_limit_ms=self.left_ms(t0) * 0.8, trace=self.trace)
            self.target, self.plan_turn = res.target, obs.turn
            self.intercepting = self.icpt is not None and res.target == self.icpt.cell
            self.chase = (self.role == TOM and self.last_seen is not None
                          and not self.intercepting and res.target == self.last_seen[0])
            nodes, algorithm = res.iterations, f"MCTS {res.iterations} iters"
            traces = [res.trace] if res.trace else []
        assert self.target is not None
        path = self.route(obs, self.target)
        action = direction(obs.self_pos, path[1]) if len(path) > 1 else "WAIT"
        return self.decision(obs, t0, mode, action, algorithm, nodes, path, [], traces)

    def scripted_move(self, obs: Observation, t0: float, mode: str) -> Decision:
        """Modes that need no search: Jerry to the kennel (RUN_FOR_BRUNO) along the same
        danger-aware route, Tom one step maximising the BFS distance from Bruno (RETREAT)."""
        self.target, self.plan_turn, self.chase, self.intercepting = None, None, False, False
        if mode == "RUN_FOR_BRUNO":
            path = self.route(obs, obs.kennel)
            action = direction(obs.self_pos, path[1]) if len(path) > 1 else "WAIT"
            return self.decision(obs, t0, mode, action, "BFS route to the kennel", 0, path, [], [])
        bruno = obs.bruno[0] if obs.bruno is not None else obs.kennel
        d_b = obs.maze.dist_map(bruno)
        action = max(moves_from(obs.maze, obs.self_pos),
                     key=lambda a: d_b[step(obs.self_pos, a)])
        return self.decision(obs, t0, mode, action, "BFS distance map (flee Bruno)", len(d_b),
                             [obs.self_pos, step(obs.self_pos, action)], [], [])

    def target_kind(self, obs: Observation, cell: Cell) -> str:
        if self.intercepting:
            return "INTERCEPT"
        if self.chase:
            return "CHASE"
        if cell in obs.key_cells:
            return "KEY"
        if cell == obs.exit_cell:
            return "EXIT"
        return "KENNEL" if cell == obs.kennel else "LAST SEEN"

    def route(self, obs: Observation, goal: Cell) -> list[Cell]:
        """Shortest path to `goal`. Jerry avoids a visible Tom and the cells next to him;
        if that cuts her off, she steps to the neighbour farthest from Tom."""
        maze, me = obs.maze, obs.self_pos
        if self.role == TOM or obs.opp_pos is None:
            path = [me]
            while path[-1] != goal:
                path.append(toward(maze, path[-1], goal))
            return path
        tom = obs.opp_pos
        res = bfs(maze.adj, me, goal, blocked={tom, *maze.adj[tom]} - {me})
        if res.path:
            return res.path
        d_tom = maze.dist_map(tom)
        cell = max((step(me, a) for a in moves_from(maze, me)), key=lambda c: d_tom[c])
        return [me, cell]

    def decision(self, obs: Observation, t0: float, mode: str, action: str, algorithm: str,
                 nodes: int, path: list[Cell], explored: list[Cell],
                 traces: list[dict]) -> Decision:
        """Assemble the Decision (fills every field; trace only when requested)."""
        ms = (time.perf_counter() - t0) * 1000
        trace = None
        if self.trace:
            trace = {"role": self.role, "turn": obs.turn, "algo": self.algo, "mode": mode,
                     "algorithm": algorithm, "action": action, "nodes": nodes, "ms": ms,
                     "target": list(self.target) if self.target else None,
                     "triggers": dict(self.triggers) if self.algo == MCTS else None,
                     "intercept": ({"cell": list(self.icpt.cell), "k": self.icpt.k,
                                    "goal": list(self.icpt.goal),
                                    "jerry_path": [list(c) for c in self.icpt.jerry_path]}
                                   if self.icpt else None),
                     "parts": traces}
        return Decision(action=action, mode=mode, algorithm=algorithm, nodes=nodes, ms=ms,
                        path=list(path), explored=list(explored), trace=trace)


def make_agent(role: str, algo: str, seed: int, trace: bool = False) -> AIAgent:
    """AI agent for `role` using `algo` (MINIMAX or MCTS)."""
    return AIAgent(role, algo, seed, trace)
