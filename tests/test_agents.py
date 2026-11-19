import ast
import gc
import inspect
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

import agents
from agents import DIFFICULTIES, JerryAgent, TomAgent, make_agent
from game import (
    JERRY,
    TOM,
    GameState,
    apply_action,
    belief_state,
    end_of_round,
    from_ascii,
    make_observation,
    new_game,
    run_round,
)
from maze import generate_maze
from scripts.match import play_one

PAIRS = [(t, j) for t in DIFFICULTIES for j in DIFFICULTIES]


def test_no_illegal_actions_300_games_all_pairs() -> None:
    """300 games spread over all 16 difficulty pairs (15x15 maps to keep the suite
    under a minute); every game must finish. apply_action raises on an illegal
    action, and play_one double-checks each one."""
    jobs = [(seed, *PAIRS[seed % len(PAIRS)], 15, True) for seed in range(300)]
    with ProcessPoolExecutor(max(1, (os.cpu_count() or 2) - 1)) as pool:
        results = list(pool.map(play_one, jobs, chunksize=4))
    assert len(results) == 300
    for job, r in zip(jobs, results, strict=True):
        assert r["illegal"] == [] and r["errors"] == [], job
        assert r["winner"] in (TOM, JERRY)


@pytest.mark.parametrize("tom, jerry", PAIRS)
def test_every_decision_fills_every_field(tom: str, jerry: str) -> None:
    state = new_game(generate_maze(5, 15))
    players = {TOM: make_agent(TOM, tom, 1, trace=True), JERRY: make_agent(JERRY, jerry, 2,
                                                                           trace=True)}
    for _ in range(25):
        if state.winner is not None:
            break
        for role in (JERRY, TOM):
            if state.winner is not None or (role == TOM and state.tom_stun):
                continue
            level = tom if role == TOM else jerry
            d = players[role].act(make_observation(state, role))
            assert d.action in ("UP", "DOWN", "LEFT", "RIGHT", "WAIT")
            assert d.mode and d.algorithm and d.nodes >= 0 and d.ms >= 0
            assert d.path and d.path[0] == (state.tom if role == TOM else state.jerry)
            if level == "EASY":
                assert d.mode == "SCRIPTED" and d.fuzzy_inputs is None
            else:
                assert d.fuzzy_inputs and d.rule_strengths
            assert d.trace is not None
            assert d.trace["parts"] or d.algorithm == "Random walk"
            json.dumps(d.trace)
            apply_action(state, role, d.action)
        end_of_round(state)


def test_agents_only_take_observations() -> None:
    for cls in (TomAgent, JerryAgent, agents.RandomAgent):
        params = list(inspect.signature(cls.act).parameters.values())
        assert [p.name for p in params] == ["self", "obs"]
        assert params[1].annotation == "Observation"
    tree = ast.parse(Path(agents.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "GameState" not in imported and "make_observation" not in imported
    # After a full game, nothing the agents hold refers to the real state.
    state = new_game(generate_maze(11, 21))
    tom, jerry = TomAgent("NIGHTMARE", 1), JerryAgent("NIGHTMARE", 2)
    for _ in range(40):
        if state.winner is None:
            run_round(state, lambda o: jerry.act(o).action, lambda o: tom.act(o).action)
    holders = {id(tom), id(jerry), id(tom.__dict__), id(jerry.__dict__)}
    assert not any(id(r) in holders for r in gc.get_referrers(state))
    assert all(not isinstance(v, GameState) for a in (tom, jerry) for v in vars(a).values())


def test_belief_state_hides_the_exit_from_tom() -> None:
    s = from_ascii("""
        #########
        #J.K..TE#
        #.#####.#
        #...H...#
        #########
    """, keys_taken=2)
    tom_view = belief_state(make_observation(s, TOM), s.jerry)
    assert tom_view.exit is None
    jerry_view = belief_state(make_observation(s, JERRY), s.tom)
    assert jerry_view.exit == s.maze.exit


def test_hard_tom_infers_jerry_from_a_vanished_key() -> None:
    s = from_ascii("""
        ###############
        #JK..........T#
        #.###########.#
        #E.....H......#
        ###############
    """, keys_taken=1)
    for level, expect in (("NORMAL", None), ("HARD", (1, 2))):
        tom = TomAgent(level, 0)
        tom.act(make_observation(s, TOM))
        s2 = s.copy()
        apply_action(s2, JERRY, "RIGHT")  # Jerry takes the key, out of Tom's sight
        tom.act(make_observation(s2, TOM))
        assert (tom.last_seen[0] if tom.last_seen else None) == expect


def test_evade_plan_finds_safe_path() -> None:
    s = from_ascii("""
        ###########
        #.........#
        #.###.###.#
        #...J...T.#
        #.###.###.#
        #K..H...E.#
        ###########
    """)
    ev = agents.evade_plan(s.maze, s.jerry, s.tom)
    assert ev.best_path and len(ev.best_path) == 6
    assert ev.action != "RIGHT"
    assert ev.trace["type"] == "dls" and ev.trace["safe_paths"] > 0
