"""Information-set Monte Carlo Tree Search for strategic targets (CLAUDE.md 4.7).

The chooser (Tom or Jerry) picks a TARGET CELL: Tom an ambush target (a
remaining key, the open exit, the kennel, Jerry's last seen cell), Jerry the
next key (or the open exit). The opponent's position is hidden, so every
iteration first DETERMINIZES: it samples one cell where the opponent could be
(a cell within `age` steps of where it was last seen that the chooser cannot
see right now). Then it runs UCT on that sampled world:

  select    UCB1 = wins/visits + c * sqrt(ln(parent visits) / visits), c = 1.4
  expand    one untried target per iteration until all are tried
  playout   at most 20 turns with cheap scripted policies, Bruno's FSM included
  backprop  add the reward (1 or 0) to the child and the root

One strategic decision is made per re-plan, so the tree has two levels: the
root (current situation) and one child per target. After the iteration budget
the child with the most visits is chosen. Every random choice uses the seeded
rng passed in, so a game replays identically. No pygame here.
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field

import config as C
from game import (
    JERRY,
    TOM,
    GameState,
    Observation,
    apply_action,
    belief_state,
    direction,
    end_of_round,
    moves_from,
    toward,
)
from search import Cell


@dataclass
class Child:
    """Statistics for one target (a level-1 node of the tree)."""

    target: Cell
    visits: int = 0
    wins: float = 0.0

    def ucb(self, parent_visits: int, c: float) -> float:
        if self.visits == 0:
            return math.inf
        return self.wins / self.visits + c * math.sqrt(math.log(parent_visits) / self.visits)


@dataclass
class MCTSResult:
    """Chosen target, per-target statistics and the determinized opponent cells."""

    target: Cell
    children: list[Child]
    iterations: int
    ms: float
    samples: Counter = field(default_factory=Counter)
    trace: dict | None = None


def _jerry_policy(s: GameState, target: Cell | None, rng: random.Random) -> str:
    """Playout Jerry: with prob. 0.8 step toward `target` (the chooser's target, or the
    nearest remaining key / known open exit), else a random neighbour."""
    if target is None:
        if s.keys:
            target = min(s.keys, key=lambda k: s.maze.dist(s.jerry, k))
        elif s.exit_open and s.exit is not None:
            target = s.exit
    moves = [a for a in moves_from(s.maze, s.jerry) if a != "WAIT"]
    if target is None or target == s.jerry or rng.random() >= 0.8:
        return rng.choice(moves) if moves else "WAIT"
    return direction(s.jerry, toward(s.maze, s.jerry, target))


def _tom_policy(s: GameState, target: Cell | None) -> str:
    """Playout Tom. As chooser: walk the shortest path to `target`, then wait.
    As opponent (target None): chase Jerry if within vision, else wait."""
    if s.tom_stun > 0:
        return "WAIT"
    if target is None:
        if s.maze.dist(s.tom, s.jerry) > C.VISION_RADIUS:
            return "WAIT"
        target = s.jerry
    return direction(s.tom, toward(s.maze, s.tom, target))


def playout(s: GameState, chooser: str, target: Cell, rng: random.Random,
            turns: int = C.MCTS_PLAYOUT_TURNS) -> float:
    """Simulate at most `turns` rounds on `s` (mutated). Reward from the chooser's view:
    Tom 1 if Jerry is caught; Jerry 1 if she reaches `target` before being caught."""
    if chooser == TOM:  # Tom decides mid-round (Jerry already moved): finish this round
        apply_action(s, TOM, _tom_policy(s, target))
        end_of_round(s)
    for _ in range(turns):
        if s.winner is not None:
            break
        apply_action(s, JERRY, _jerry_policy(s, target if chooser == JERRY else None, rng))
        if chooser == JERRY and s.jerry == target and s.winner != TOM:
            return 1.0
        if s.winner is None:
            apply_action(s, TOM, _tom_policy(s, target if chooser == TOM else None))
        end_of_round(s)
    if chooser == TOM:
        return 1.0 if s.winner == TOM and s.jerry == s.tom else 0.0
    return 0.0


def opponent_cells(obs: Observation, last_seen: tuple[Cell, int] | None) -> list[Cell]:
    """Information set: cells where the opponent can be, given what `obs.role` knows.

    Visible -> exactly that cell. Seen `age` turns ago at L -> floor cells within
    path distance `age` of L that are not visible now (an empty visible cell
    cannot hold the opponent). Never seen -> every floor cell not visible now.
    """
    if obs.opp_pos is not None:
        return [obs.opp_pos]
    maze = obs.maze
    if last_seen is None:
        cells = [c for c in sorted(maze.floor) if c not in obs.visible_cells]
    else:
        cell, seen_turn = last_seen
        age = obs.turn - seen_turn
        cells = sorted(c for c, d in maze.dist_map(cell).items()
                       if d <= age and c not in obs.visible_cells)
    return cells or [last_seen[0] if last_seen else obs.self_pos]


def mcts(obs: Observation, targets: list[Cell], opp_cells: list[Cell], rng: random.Random,
         iterations: int = C.MCTS_ITERATIONS, c: float = C.MCTS_UCB_C,
         bruno_activations: int = 0, time_limit_ms: float | None = None,
         trace: bool = False) -> MCTSResult:
    """Information-set UCT over strategic `targets` for `obs.role`.

    Where used: NIGHTMARE Tom (ambush target) and NIGHTMARE Jerry (next key),
    re-planned every 5 turns or when the opponent is newly seen; the MCTS view
    of the algorithm demo. `time_limit_ms` is only a safety net: normally all
    `iterations` run, so results are reproducible.
    """
    t0 = time.perf_counter()
    base = belief_state(obs, opp_cells[0], bruno_activations)
    kids = [Child(t) for t in targets]
    untried = list(range(len(kids)))
    root_visits = 0
    root_wins = 0.0
    samples: Counter = Counter()
    done = 0
    for _ in range(iterations):
        if time_limit_ms and (time.perf_counter() - t0) * 1000 > time_limit_ms:
            break
        opp = rng.choice(opp_cells)  # determinization
        samples[opp] += 1
        s = base.copy(history=False)
        if obs.role == TOM:
            s.jerry = opp
        else:
            s.tom = opp
        if untried:  # expansion: one new child per iteration
            child = kids[untried.pop(rng.randrange(len(untried)))]
        else:  # selection: UCB1
            child = max(kids, key=lambda k: k.ucb(root_visits, c))
        reward = playout(s, obs.role, child.target, rng)
        child.visits += 1
        child.wins += reward
        root_visits += 1
        root_wins += reward
        done += 1
    # most visits; ties (e.g. no playout ever scored) go to the earliest target in
    # `targets`, which callers order by their heuristic preference
    best = max(kids, key=lambda k: (k.visits, k.wins))
    res = MCTSResult(best.target, kids, done, (time.perf_counter() - t0) * 1000, samples)
    if trace:
        res.trace = {
            "type": "mcts", "role": obs.role, "iterations": done, "chosen": list(best.target),
            "root_children": [{"target": list(k.target), "visits": k.visits, "wins": k.wins,
                               "win_rate": k.wins / k.visits if k.visits else 0.0,
                               "ucb": _num(k.ucb(root_visits, c))} for k in kids],
            "tree": [{"id": 0, "parent": None, "target": None, "visits": root_visits,
                      "wins": root_wins, "ucb": None}]
            + [{"id": i + 1, "parent": 0, "target": list(k.target), "visits": k.visits,
                "wins": k.wins, "ucb": _num(k.ucb(root_visits, c))} for i, k in enumerate(kids)],
            "samples": [[list(cell), n] for cell, n in sorted(samples.items())],
        }
    return res


def _num(x: float) -> float | str:
    return x if math.isfinite(x) else "inf"
