import json
import random

from game import JERRY, TOM, from_ascii, make_observation
from mcts import mcts, opponent_cells


def test_jerry_picks_the_key_away_from_tom() -> None:
    # Right key sits next to Tom; the left key is just as close and safe.
    s = from_ascii("""
        #############
        #K....J...KT#
        #.###########
        #E....H.....#
        #############
    """)
    obs = make_observation(s, JERRY)
    assert obs.opp_pos == (1, 11)
    res = mcts(obs, [(1, 1), (1, 10)], opponent_cells(obs, None), random.Random(1))
    assert res.target == (1, 1)
    best = {c.target: c.wins / c.visits for c in res.children}
    assert best[(1, 1)] > best[(1, 10)]


def test_tom_ambushes_the_key_jerry_walks_to() -> None:
    # Jerry walks the top corridor to the last key. Tom is 4 steps from it.
    # Going to her last seen cell takes the bottom route and misses her.
    s = from_ascii("""
        ###############
        #J...........K#
        #.###########.#
        #.###########.#
        #E.....H....T.#
        ###############
    """)
    obs = make_observation(s, TOM)
    assert obs.opp_pos is None
    targets = [(1, 13), obs.kennel, (1, 1)]
    res = mcts(obs, targets, [(1, 1)], random.Random(2))
    assert res.target == (1, 13)


def test_tom_guards_the_open_exit() -> None:
    s = from_ascii("""
        ###############
        #J...........E#
        #.###########.#
        #.###########.#
        #......H....T.#
        ###############
    """)
    obs = make_observation(s, TOM)
    assert obs.exit_open and obs.exit_cell == (1, 13)
    res = mcts(obs, [(1, 13), obs.kennel, (1, 1)], [(1, 1)], random.Random(3), trace=True)
    assert res.target == (1, 13)
    tr = res.trace
    assert tr is not None and tr["type"] == "mcts" and tr["iterations"] == 300
    assert sum(c["visits"] for c in tr["root_children"]) == 300
    assert tr["tree"][0]["visits"] == 300
    json.dumps(tr)


def test_same_seed_same_result() -> None:
    s = from_ascii("""
        #############
        #K....J...KT#
        #.###########
        #E....H.....#
        #############
    """)
    obs = make_observation(s, TOM)
    a = mcts(obs, [(1, 1), (1, 10), obs.kennel], [(1, 6)], random.Random(9))
    b = mcts(obs, [(1, 1), (1, 10), obs.kennel], [(1, 6)], random.Random(9))
    assert [(c.visits, c.wins) for c in a.children] == [(c.visits, c.wins) for c in b.children]


def test_information_set_excludes_visible_cells() -> None:
    s = from_ascii("""
        ###############
        #J...........K#
        #.###########.#
        #.###########.#
        #E.....H....T.#
        ###############
    """)
    obs = make_observation(s, TOM)
    cells = opponent_cells(obs, ((1, 1), obs.turn - 3))
    assert (1, 1) in cells and (4, 1) in cells
    assert all(c not in obs.visible_cells for c in cells)
    assert all(s.maze.dist((1, 1), c) <= 3 for c in cells)
