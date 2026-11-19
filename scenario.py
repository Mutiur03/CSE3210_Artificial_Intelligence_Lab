"""Fixed teaching scenarios for the evaluation (CLAUDE.md section 6). No randomness.

`build_scenario` sets up ONE hand-made 13x13 position, asks both HARD agents to
decide on it with `trace=True`, and also runs the mode handlers that the close-range
minimax overrides (Tom's HUNT A*, Jerry's DLS evade, Jerry's A* to the kennel) plus
MCTS and the exact minimax tables, all through the same functions the agents call.
`build_bruno_scenario` replays a tiny game where Bruno bites Tom.
`python scenario.py` (make scenario) writes every file in docs/scenario/ through
scenario_report.build_all. No pygame here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from pathlib import Path

import minimax
from agents import Decision, EvadeResult, JerryAgent, Plan, TomAgent, evade_plan, make_agent
from game import (
    JERRY,
    TOM,
    GameState,
    Observation,
    belief_state,
    direction,
    from_ascii,
    make_observation,
    render_ascii,
    run_round,
    toward,
)
from mcts import MCTSResult, mcts, opponent_cells
from search import Cell, SearchResult, astar, greedy_best_first

SEED = 7  # agent seeds; HARD never draws from them, MCTS gets Random(SEED)
TURN = 18
HIDDEN_AGE = 6  # MCTS information-set variant: Jerry unseen for this many turns

#   Jerry (6,5) and Tom (6,8) stand in the middle corridor, path distance 3.
#   West of Jerry is the junction (6,1): north to the last key K, south to the kennel H.
#   (7,5)-(8,5) is a dead-end stub right below Jerry. The exit E is locked (2 keys taken).
MAP = """
#############
#...........#
#K#########.#
#.#########E#
#.#########.#
#.#########.#
#....J..T...#
#.###.#####.#
#H###.#####.#
#.#########.#
#.#########.#
#...........#
#############
"""

BRUNO_MAP = """
###########
#H.......K#
#.........#
#...J..T.E#
###########
"""


@dataclass
class Compare:
    """A* and greedy best-first on the same start / goal (unit cost, Manhattan)."""

    label: str
    start: Cell
    goal: Cell
    astar: SearchResult
    greedy: SearchResult


@dataclass
class Scenario:
    """Everything the report writes, computed once from the live code."""

    state: GameState
    obs: dict[str, Observation]
    decisions: dict[str, Decision]  # what the HARD agents really chose (trace=True)
    hunt: Plan  # Tom: the A* HUNT would run (fuzzy picked HUNT, minimax overrode it)
    kennel_run: Plan  # Jerry: the A* RUN_FOR_BRUNO would run
    evade: EvadeResult  # Jerry: the DLS EVADE would run
    minimax: dict[str, minimax.MinimaxResult]  # iterative deepening, trace=True
    root: dict[str, list[minimax.RootMove]]  # exact value of each root action
    mcts_seen: MCTSResult  # Tom's MCTS on the real observation (Jerry visible)
    mcts_hidden: MCTSResult  # Tom's MCTS if Jerry had been unseen for HIDDEN_AGE turns
    hidden_obs: Observation
    jerry_goal: Cell
    compare: list[Compare] = field(default_factory=list)


def build_scenario() -> Scenario:
    """Run both agents and every supporting analysis on the fixed position."""
    state = from_ascii(MAP, turn=TURN)
    maze = state.maze
    obs = {role: make_observation(state, role) for role in (TOM, JERRY)}
    decisions = {role: make_agent(role, "HARD", SEED, trace=True).act(obs[role])
                 for role in (TOM, JERRY)}

    # supporting analyses on fresh agents, so memory (last seen) is the same as above
    tom = TomAgent("HARD", SEED, trace=True)
    tom.remember(obs[TOM])
    jerry = JerryAgent("HARD", SEED, trace=True)
    jerry.remember(obs[JERRY])
    hunt = tom.hunt(obs[TOM])
    kennel_run = jerry.run_to(obs[JERRY], obs[JERRY].kennel)
    evade = evade_plan(maze, state.jerry, state.tom)
    goal = jerry.goal(obs[JERRY])

    mm, root = {}, {}
    for role in (TOM, JERRY):
        belief = belief_state(obs[role], obs[role].opp_pos or state.tom)
        mm[role] = minimax.decide(belief, role, trace=True)
        root[role] = minimax.root_moves(belief, role)

    targets = tom.mcts_targets(obs[TOM])
    seen = mcts(obs[TOM], targets, opponent_cells(obs[TOM], tom.last_seen),
                random.Random(SEED), trace=True)
    hidden = replace(obs[TOM], opp_pos=None, turn=obs[TOM].turn + HIDDEN_AGE)
    hid = mcts(hidden, tom.mcts_targets(hidden), opponent_cells(hidden, tom.last_seen),
               random.Random(SEED), trace=True)

    pairs = [("Tom -> Jerry (HUNT)", state.tom, state.jerry),
             ("Jerry -> last key", state.jerry, goal),
             ("Jerry -> kennel", state.jerry, maze.kennel),
             ("Jerry -> exit", state.jerry, maze.exit),
             ("Tom -> last key", state.tom, goal),
             ("Tom -> cell (1,5), decoy", state.tom, (1, 5))]
    compare = [Compare(label, a, b, astar(maze.adj, a, b), greedy_best_first(maze.adj, a, b))
               for label, a, b in pairs]
    return Scenario(state, obs, decisions, hunt, kennel_run, evade, mm, root, seen, hid,
                    hidden, goal, compare)


# ------------------------------------------------------------------ Bruno saves Jerry


@dataclass
class Frame:
    """One round of the Bruno scenario: ASCII picture, state summary, what happened."""

    round: int
    ascii: str
    jerry: Cell
    tom: Cell
    bruno: Cell
    bruno_state: str
    tom_stun: int
    events: list[str]


def build_bruno_scenario() -> tuple[GameState, list[Frame]]:
    """Jerry walks onto the kennel with Tom 3 cells behind; Bruno wakes, chases, bites.

    Scripted policies: Jerry walks to the kennel and waits, Tom walks toward Jerry
    (BFS step). Frames run from the start until Tom's stun is over.
    """
    state = from_ascii(BRUNO_MAP, keys_taken=2)

    def jerry(o: Observation) -> str:
        return "WAIT" if o.self_pos == o.kennel else direction(
            o.self_pos, toward(o.maze, o.self_pos, o.kennel))

    def tom(o: Observation) -> str:
        return "WAIT" if o.opp_pos is None else direction(
            o.self_pos, toward(o.maze, o.self_pos, o.opp_pos))

    def frame(n: int, events: list[str]) -> Frame:
        b = state.bruno
        assert b is not None
        return Frame(n, render_ascii(state), state.jerry, state.tom, b.pos, b.state,
                     state.tom_stun, events)

    frames = [frame(0, [])]
    bitten = False
    while state.winner is None and len(frames) < 30:
        events = [e.text for e in run_round(state, jerry, tom)]
        frames.append(frame(len(frames), events))
        bitten = bitten or state.bites > 0
        if bitten and state.tom_stun == 0:
            break
    return state, frames


def main(out: str = "docs/scenario") -> None:
    from scenario_report import build_all  # imports matplotlib, only needed here
    files = build_all(Path(out))
    print(f"wrote {len(files)} files to {out}/")


if __name__ == "__main__":
    main()
