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


@pytest.mark.parametrize("level", ["EASY", "NORMAL", "HARD"])
def test_tom_leaves_his_start_when_jerry_is_unseen(level: str) -> None:
    """Regression: SWEEP rooted its DFS at Tom's own cell and he paced UP/DOWN at the start;
    EASY's random walk waited and froze in dead ends. Tom must travel in the opening."""
    seeds = [1, 3, 5, 8, 9, 11, 14, 18, 20, 22]  # seeds that used to pace or freeze
    for seed in seeds:
        state = new_game(generate_maze(seed))
        tom, jerry = make_agent(TOM, level, seed * 2 + 1), make_agent(JERRY, "NORMAL", seed * 2)
        start, reach = state.tom, 0
        for _ in range(12):
            run_round(state, lambda o, j=jerry: j.act(o).action,
                      lambda o, t=tom: t.act(o).action)
            reach = max(reach, state.maze.dist(start, state.tom))
            if state.winner is not None:
                break
        assert reach >= 4, (level, seed, reach)


def test_sweep_checks_the_last_key_first() -> None:
    """With one key left Jerry must come to it, so a Tom who lost her sweeps there first
    (it used to sweep the nearest side branch while she walked to the key)."""
    s = from_ascii("""
        #####################
        #T..........K......J#
        #.###################
        #E.......H..........#
        #####################
    """, keys_taken=2)
    d = TomAgent("NORMAL", 0).act(make_observation(s, TOM))
    assert d.mode == "SWEEP" and d.action == "RIGHT"  # toward the key, not down the side branch


def test_ambush_wait_is_capped_and_labelled() -> None:
    """Tom waits in ambush at most AMBUSH_MAX_WAIT turns with no sign of Jerry, saying so,
    then sweeps (he used to stand still for 13 turns)."""
    s = from_ascii("""
        #############
        #.TK.......J#
        #E.......H..#
        #############
    """, keys_taken=2)
    apply_action(s, TOM, "RIGHT")  # Tom stands on the last key; Jerry is out of sight
    tom = TomAgent("HARD", 0)
    tom.last_seen = ((1, 11), s.turn - 6)  # stale sighting: fuzzy picks AMBUSH
    algos = [tom.act(make_observation(s, TOM)) for _ in range(agents.C.AMBUSH_MAX_WAIT + 2)]
    cap = agents.C.AMBUSH_MAX_WAIT
    assert all("waiting in ambush" in d.algorithm for d in algos[:cap])
    assert all("ambush wait limit" in d.algorithm for d in algos[cap:])
    assert all(d.mode == "AMBUSH" for d in algos)
