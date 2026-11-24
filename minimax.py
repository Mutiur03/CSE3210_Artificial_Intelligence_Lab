"""Minimax with alpha-beta pruning: the MINIMAX agent's move every turn (CLAUDE.md 4.6).

The game tree is a local sub-game built from the agent's own observation
(game.belief_state). Plies alternate between the two characters; Tom is MAX,
Jerry is MIN, every value is from Tom's point of view. After every Tom ply the
round ends: Bruno takes his scripted FSM step and timers tick (game.end_of_round),
so Bruno acts once per full round (every 2 plies). A stunned Tom can only WAIT.

`plain_minimax` (no pruning) and `alphabeta` search a fixed depth and are
compared in the tests. `decide` is what the agents call: iterative deepening
alpha-beta (depth 1, 2, .. 4) with a node cap and a time safety net; if a limit
hits mid-iteration it returns the result of the last completed depth.
No pygame here.
"""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

import config as C
from game import TOM, GameState, apply_action, end_of_round, legal_actions, other
from search import Cell

TRACE_PLIES = 3  # plies recorded in full in the trace tree
TRACE_MAX_NODES = 200
WIN = 1000


@dataclass
class MinimaxResult:
    """Chosen root action, its value, and search statistics.

    `pv` = principal variation as (player, action, tom cell, jerry cell) per ply.
    `explored` = cells either character stood on somewhere in the tree (first-seen order).
    """

    action: str
    value: float
    nodes: int
    depth: int
    ms: float
    pv: list[tuple[str, str, Cell, Cell]]
    explored: list[Cell]
    terms: dict = field(default_factory=dict)
    trace: dict | None = None


@dataclass(frozen=True)
class Tune:
    """Fuzzy-mode adjustment of the evaluation: factors on the distance, goal, escape and
    Bruno terms, and an optional goal cell for Jerry (e.g. the kennel). Default = no change."""

    dist: float = 1.0
    goal: float = 1.0
    escape: float = 1.0
    bruno: float = 1.0
    goal_cell: Cell | None = None
    aim: Cell | None = None  # Tom's interception cell: the evaluation rewards being near it
    aim_w: float = 0.0  # weight per step of d(Tom, aim) (negative = closer is better)
    key_w: float = C.W_KEYS  # value of one collected key, set per decision (with_key_weight)


def _goal(state: GameState, tune: Tune = Tune()) -> Cell | None:
    """Jerry's goal: nearest remaining key she reaches before Tom (else the nearest), else the
    exit if open and known
    (a mode may override it with `tune.goal_cell`)."""
    if tune.goal_cell is not None:
        return tune.goal_cell
    if state.keys:
        m = state.maze  # a key Tom reaches first is a trap: prefer the nearest key she wins
        safe = [k for k in state.keys if m.dist(state.jerry, k) < m.dist(state.tom, k)]
        return min(safe or state.keys, key=lambda k: m.dist(state.jerry, k))
    return state.exit if state.exit_open else None


def key_weight(maze_dist, keys: Iterable[Cell], exit_cell: Cell | None,
               goal_factor: float = 1.0) -> float:
    """Value of one collected key (Tom's view, negative = good for Jerry).

    W_KEYS plus the largest jump of the goal term a collection can cause: after a
    key Jerry stands on a key cell and her goal moves to another remaining key or
    the exit, at most `span` steps away (longest path between two of those cells).
    Without this, a mode that scales the goal term (SNEAK x3) made a far next key
    cost more than the key was worth, and Jerry hovered next to a key forever.
    `maze_dist(a, b)` = path distance.
    """
    cells = [*keys, *([exit_cell] if exit_cell is not None else [])]
    span = max((maze_dist(a, b) for a, b in itertools.combinations(cells, 2)), default=0)
    return C.W_KEYS - goal_factor * C.W_GOAL * span


def with_key_weight(state: GameState, tune: Tune) -> Tune:
    """`tune` with `key_w` fixed from the root position, so every leaf of one search
    values a key the same. Called by `decide` and `root_moves`."""
    return replace(tune, key_w=key_weight(state.maze.dist, state.keys, state.exit, tune.goal))


def evaluate(state: GameState, tune: Tune = Tune()) -> tuple[float, dict]:
    """Static evaluation from Tom's view (weights in config.py, formula in CLAUDE.md 4.6).

    E = -10*near + -1*far + 2*d(Jerry,goal) + key_weight*keys_taken - 3*escape_routes(Jerry)
        - 15*bruno_guard_near_tom - 8*tom_stun + 5*[Jerry in a dead end]
    near = min(d(Tom,Jerry), 8), far = the rest: beyond 8 steps the threat fades, so
    a Jerry far from Tom walks to her keys instead of only running away, while Tom
    still has a (weaker) pull toward her.
    escape_routes = Jerry's neighbour cells that Tom cannot reach in one step
    (d(Tom, cell) > d(Jerry, cell) = 1). Escape routes and the dead-end term only
    matter while Tom is within NEAR_DIST; farther away escape counts as the maximum 4
    and dead ends are free, else Jerry would never walk into a dead end for a key.
    """
    m, b = state.maze, state.bruno
    goal = _goal(state, tune)
    dist = m.dist(state.tom, state.jerry)
    threat = dist <= C.NEAR_DIST
    terms = {
        "dist": dist,
        "goal": m.dist(state.jerry, goal) if goal is not None else 0,
        "keys": state.keys_taken,
        "escape": sum(1 for n in m.adj[state.jerry] if m.dist(state.tom, n) > 1) if threat else 4,
        "bruno_near": int(b is not None and b.state in ("GUARD", "CHASE_CAT")
                          and m.dist(b.pos, state.tom) <= C.BRUNO_CHASE_TRIGGER_DIST),
        "stun": state.tom_stun,
        "dead_end": int(threat and state.jerry in m.dead_ends),
    }
    near = min(dist, C.NEAR_DIST)
    if tune.aim is not None:
        terms["aim"] = m.dist(state.tom, tune.aim)
    value = (tune.aim_w * terms.get("aim", 0)
             + tune.dist * (C.W_DIST * near + C.W_DIST_FAR * (dist - near))
             + tune.key_w * terms["keys"] + tune.goal * C.W_GOAL * terms["goal"]
             + tune.escape * C.W_ESCAPE * terms["escape"]
             + tune.bruno * C.W_BRUNO_NEAR * terms["bruno_near"] + C.W_STUN * terms["stun"]
             + C.W_DEAD_END * terms["dead_end"])
    return value, terms


def children(state: GameState, player: str) -> list[tuple[str, GameState]]:
    """(action, next state) for every legal action, in search order.

    Move ordering: Tom tries moves that bring him closest to Jerry first, Jerry
    tries moves that take her farthest from Tom first; WAIT always last. Good
    moves first means alpha-beta prunes more.
    """
    out = []
    for action in legal_actions(state, player):
        child = state.copy(history=False)
        apply_action(child, player, action)
        if player == TOM and child.winner is None:
            end_of_round(child)  # Bruno's step + timers close the round
        out.append((action, child))
    sign = 1 if player == TOM else -1

    def order(item: tuple[str, GameState]) -> tuple[int, float]:
        a, s = item
        if s.winner is not None:  # winning / losing moves are decisive: look first
            return (-1, 0)
        return (int(a == "WAIT"), sign * s.maze.dist(s.tom, s.jerry))

    out.sort(key=order)
    return out


class _Limit(Exception):
    """Node cap or time limit reached inside an iteration."""


class _Search:
    """One fixed-depth search. alphabeta=False gives plain minimax."""

    def __init__(self, depth: int, alphabeta: bool, node_cap: int | None,
                 deadline: float | None, record: bool, tune: Tune = Tune()) -> None:
        self.depth, self.alphabeta, self.tune = depth, alphabeta, tune
        self.node_cap, self.deadline = node_cap, deadline
        self.nodes = 0
        self.tree: list[dict] | None = [] if record else None
        self.explored: dict[Cell, None] = {}

    def _record(self, parent: int | None, ply: int, player: str, move: str | None,
                alpha: float, beta: float, pruned: bool = False) -> dict | None:
        if self.tree is None or ply > TRACE_PLIES or len(self.tree) >= TRACE_MAX_NODES:
            return None
        node = {"id": len(self.tree), "parent": parent, "ply": ply, "player": player,
                "move": move, "value": None, "alpha": _num(alpha), "beta": _num(beta),
                "pruned": pruned, "terminal": False, "eval_terms": None}
        self.tree.append(node)
        return node

    def value(self, state: GameState, player: str, ply: int, alpha: float, beta: float,
              parent: int | None, move: str | None) -> tuple[float, dict, list]:
        """Value of `state` with `player` to move. Returns (value, PV-leaf terms, PV)."""
        self.nodes += 1
        if self.node_cap is not None and self.nodes > self.node_cap:
            raise _Limit
        if self.deadline is not None and time.perf_counter() > self.deadline:
            raise _Limit
        self.explored.setdefault(state.tom)
        self.explored.setdefault(state.jerry)
        node = self._record(parent, ply, player, move, alpha, beta)
        if state.winner is not None:
            val = WIN - ply if state.winner == TOM else -WIN + ply
            terms = {"terminal": "capture" if state.winner == TOM else "escape"}
            pv: list = []
        elif ply == self.depth:
            val, terms = evaluate(state, self.tune)
            pv = []
        else:
            val, terms, pv = self._expand(state, player, ply, alpha, beta, node)
        if node is not None:
            node["value"] = val
            node["terminal"] = state.winner is not None
            node["eval_terms"] = terms
        return val, terms, pv

    def _expand(self, state: GameState, player: str, ply: int, alpha: float, beta: float,
                node: dict | None) -> tuple[float, dict, list]:
        maximize = player == TOM
        best = -math.inf if maximize else math.inf
        best_terms: dict = {}
        best_pv: list = []
        kids = children(state, player)
        node_id = node["id"] if node is not None else None
        for i, (action, child) in enumerate(kids):
            v, terms, pv = self.value(child, other(player), ply + 1, alpha, beta, node_id, action)
            if (v > best) if maximize else (v < best):
                best, best_terms = v, terms
                best_pv = [(player, action, child.tom, child.jerry)] + pv
            if maximize:
                alpha = max(alpha, best)
            else:
                beta = min(beta, best)
            if self.alphabeta and alpha >= beta:
                for rest, _ in kids[i + 1:]:  # siblings never searched
                    self._record(node_id, ply + 1, other(player), rest, alpha, beta, pruned=True)
                break
        return best, best_terms, best_pv


def _num(x: float) -> float | str:
    """JSON-friendly number (infinities as strings)."""
    return x if math.isfinite(x) else ("inf" if x > 0 else "-inf")


def _run(state: GameState, player: str, depth: int, alphabeta_on: bool,
         node_cap: int | None = None, deadline: float | None = None,
         record: bool = False) -> tuple[MinimaxResult, _Search]:
    t0 = time.perf_counter()
    s = _Search(depth, alphabeta_on, node_cap, deadline, record)
    val, terms, pv = s.value(state, player, 0, -math.inf, math.inf, None, None)
    action = pv[0][1] if pv else "WAIT"
    res = MinimaxResult(action, val, s.nodes, depth, (time.perf_counter() - t0) * 1000, pv,
                        list(s.explored), terms)
    return res, s


def plain_minimax(state: GameState, player: str, depth: int = C.MINIMAX_DEPTH) -> MinimaxResult:
    """Minimax without pruning: every node of the depth-limited tree is visited.

    What: MAX (Tom) takes the largest child value, MIN (Jerry) the smallest;
    leaves get the static evaluation, finished games get +-(1000 - ply).
    Where used: tests and the experiments, as the reference alpha-beta must equal.
    """
    return _run(state, player, depth, alphabeta_on=False)[0]


def alphabeta(state: GameState, player: str, depth: int = C.MINIMAX_DEPTH) -> MinimaxResult:
    """Minimax with alpha-beta pruning (fixed depth).

    What: alpha = best value MAX can already force, beta = best value MIN can
    already force. When alpha >= beta at a node, the remaining siblings cannot
    change the result and are skipped. Same value as plain minimax, fewer nodes.
    Where used: the MINIMAX agents (Tom or Jerry) every turn, through `decide`.
    """
    return _run(state, player, depth, alphabeta_on=True)[0]


def decide(state: GameState, player: str, depth: int = C.MINIMAX_DEPTH,
           node_cap: int = C.MINIMAX_NODE_CAP, time_limit_ms: float | None = None,
           trace: bool = False, tune: Tune = Tune()) -> MinimaxResult:
    """Iterative-deepening alpha-beta: search depth 1, 2, ..., `depth`.

    Where used: every move of a MINIMAX agent (agents.AIAgent), and the minimax
    view of the algorithm demo. Node cap (and
    a time limit as safety net) stop an iteration; the last completed depth wins.
    `nodes` counts every node of every iteration.
    """
    t0 = time.perf_counter()
    tune = with_key_weight(state, tune)
    deadline = t0 + time_limit_ms / 1000 if time_limit_ms else None
    best: MinimaxResult | None = None
    best_tree: list[dict] | None = None
    total = 0
    for d in range(1, depth + 1):
        # depth 1 always runs to completion so there is always a move
        limited = d > 1
        s = _Search(d, True, node_cap - total if limited else None,
                    deadline if limited else None, trace, tune)
        try:
            val, terms, pv = s.value(state, player, 0, -math.inf, math.inf, None, None)
        except _Limit:
            total += s.nodes
            break
        total += s.nodes
        best = MinimaxResult(pv[0][1] if pv else "WAIT", val, 0, d, 0.0, pv,
                             list(s.explored), terms)
        best_tree = s.tree
    assert best is not None
    best.nodes = total
    best.ms = (time.perf_counter() - t0) * 1000
    if trace:
        best.trace = {"type": "minimax", "depth": best.depth, "alphabeta": True,
                      "nodes": total, "chosen": best.action, "root_player": player,
                      "value": best.value, "tree": best_tree}
    return best


@dataclass
class RootMove:
    """Exact minimax value of one root action (see `root_moves`)."""

    action: str
    value: float
    nodes: int
    terms: dict  # static-evaluation terms of the principal-variation leaf
    pv: list[tuple[str, str, Cell, Cell]]


def root_moves(state: GameState, player: str, depth: int = C.MINIMAX_DEPTH,
               tune: Tune = Tune()) -> list[RootMove]:
    """Search every root action with a full alpha-beta window, so each value is exact.

    `decide` only bounds the moves it prunes; this gives the true value, principal
    variation and leaf evaluation terms of each, for the worked tables of the
    scenario report. Where used: scenario.py.
    """
    out = []
    tune = with_key_weight(state, tune)
    for action, child in children(state, player):
        s = _Search(depth, True, None, None, False, tune)
        val, terms, pv = s.value(child, other(player), 1, -math.inf, math.inf, None, action)
        out.append(RootMove(action, val, s.nodes, terms, [(player, action, child.tom,
                                                          child.jerry)] + pv))
    return out
