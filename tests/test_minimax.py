import json
import random

import minimax
from game import CHASE_CAT, GUARD, JERRY, TOM, from_ascii, new_game
from maze import generate_maze


def _random_positions(n: int) -> list:
    """Small random tactical positions on 15x15 mazes: Tom within 6 of Jerry."""
    rng = random.Random(7)
    out = []
    seed = 0
    while len(out) < n:
        maze = generate_maze(seed, 15)
        seed += 1
        floor = sorted(maze.floor)
        jerry = rng.choice(floor)
        near = [c for c, d in maze.dist_map(jerry).items() if 1 <= d <= 6]
        s = new_game(maze, bruno_enabled=rng.random() < 0.5)
        s.jerry, s.tom = jerry, rng.choice(near)
        if s.bruno is not None:
            s.bruno.pos = rng.choice(near)
            s.bruno.state = rng.choice([GUARD, CHASE_CAT])
            s.bruno.guard_timer = 10
        s.tom_stun = rng.choice([0, 0, 0, 2])
        if s.jerry in s.keys:
            continue
        out.append((s, rng.choice([TOM, JERRY])))
    return out


def test_alphabeta_equals_plain_minimax_with_fewer_nodes() -> None:
    plain_total = ab_total = 0
    for state, player in _random_positions(30):
        p = minimax.plain_minimax(state, player, 4)
        a = minimax.alphabeta(state, player, 4)
        assert a.value == p.value
        assert a.nodes <= p.nodes
        plain_total += p.nodes
        ab_total += a.nodes
    assert ab_total < plain_total


def test_tom_takes_the_capture() -> None:
    s = from_ascii("""
        #######
        #JT...#
        #.###.#
        #K..HE#
        #######
    """)
    res = minimax.decide(s, TOM)
    assert res.action == "LEFT" and res.value > 900


def test_jerry_avoids_the_dead_end() -> None:
    # Jerry at a junction: UP leads into a dead end (Tom follows and wins),
    # LEFT keeps her in the loop.
    s = from_ascii("""
        #########
        ###.#####
        #..J...T#
        #.#####.#
        #..HK..E#
        #########
    """, bruno=False)
    res = minimax.decide(s, JERRY)
    assert res.action != "UP"


def test_iterative_deepening_respects_node_cap() -> None:
    state, player = _random_positions(1)[0]
    res = minimax.decide(state, player, node_cap=8)
    assert res.depth < 4


def test_trace_tree_shape() -> None:
    state, player = _random_positions(3)[2]
    res = minimax.decide(state, player, trace=True)
    tr = res.trace
    assert tr is not None and tr["type"] == "minimax" and tr["chosen"] == res.action
    tree = tr["tree"]
    assert 0 < len(tree) <= minimax.TRACE_MAX_NODES
    assert tree[0]["parent"] is None and tree[0]["ply"] == 0
    assert all(n["ply"] <= minimax.TRACE_PLIES for n in tree)
    leaves = [n for n in tree if n["ply"] == minimax.TRACE_PLIES and not n["pruned"]]
    assert leaves and all(n["eval_terms"] for n in leaves)
    json.dumps(tr)


def test_evaluation_terms() -> None:
    s = from_ascii("""
        #######
        #J..T.#
        #.###.#
        #K..HE#
        #######
    """, bruno=False)
    value, terms = minimax.evaluate(s)
    # d(Tom,Jerry)=3, goal = key at distance 2, escape routes 2 (right, down), no Bruno
    assert terms == {"dist": 3, "goal": 2, "escape": 2, "bruno_near": 0, "stun": 0,
                     "dead_end": 0}
    assert value == -10 * 3 + 2 * 2 - 3 * 2
