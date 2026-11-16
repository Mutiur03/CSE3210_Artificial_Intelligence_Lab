"""Phase 2: search.py on 300 random mazes and hand-made grids."""

from __future__ import annotations

import math
import random

import pytest

from maze import generate_maze, neighbours
from search import (
    CUTOFF,
    FAIL,
    FOUND,
    astar,
    bfs,
    bfs_distance_map,
    bidirectional_bfs,
    dead_end_cells,
    dfs,
    dls,
    dls_safe_paths,
    flood_fill_count,
    greedy_best_first,
    iddfs,
    reachable,
)


def grid_from(text: str) -> dict:
    """'#' wall, anything else floor. Returns adjacency in UP, DOWN, LEFT, RIGHT order."""
    rows = [r for r in text.strip("\n").splitlines()]
    floor = frozenset((r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch != "#")
    return {cell: neighbours(floor, cell) for cell in floor}


def is_walk(adj: dict, path: list) -> bool:
    return all(b in adj[a] for a, b in zip(path, path[1:], strict=False))


@pytest.fixture(scope="module")
def cases() -> list:
    """300 mazes (sizes 15..31) with a seeded random start/goal pair each."""
    rng = random.Random(2)
    out = []
    for seed in range(300):
        m = generate_maze(seed, rng.choice((15, 21, 27, 31)))
        cells = sorted(m.floor)
        out.append((m.adj, rng.choice(cells), rng.choice(cells)))
    return out


def test_astar_matches_bfs_length(cases) -> None:
    for adj, s, g in cases:
        a, b = astar(adj, s, g), bfs(adj, s, g)
        assert len(a.path) == len(b.path) and a.cost == b.cost
        assert a.path[0] == s and a.path[-1] == g and is_walk(adj, a.path)


def test_greedy_finds_path_never_shorter_than_astar(cases) -> None:
    for adj, s, g in cases:
        gr, a = greedy_best_first(adj, s, g), astar(adj, s, g)
        assert gr.path and gr.path[-1] == g and is_walk(adj, gr.path)
        assert len(gr.path) >= len(a.path)


def test_bidirectional_matches_bfs_and_expands_fewer(cases) -> None:
    bi_nodes = bfs_nodes = 0
    for adj, s, g in cases:
        bi, b = bidirectional_bfs(adj, s, g), bfs(adj, s, g)
        assert len(bi.path) == len(b.path) and is_walk(adj, bi.path)
        assert bi.path[0] == s and bi.path[-1] == g and bi.meeting in bi.path
        bi_nodes += bi.nodes_expanded
        bfs_nodes += b.nodes_expanded
    assert bi_nodes < bfs_nodes


def test_iddfs_and_dfs_find_paths(cases) -> None:
    for adj, s, g in cases[:60]:
        i, d, b = iddfs(adj, s, g), dfs(adj, s, g), bfs(adj, s, g)
        assert len(i.path) == len(b.path) and is_walk(adj, i.path)
        assert d.path[-1] == g and is_walk(adj, d.path) and len(d.path) >= len(b.path)


def test_astar_extra_cost_avoids_expensive_cell() -> None:
    adj = grid_from("""
#####
#...#
#.#.#
#...#
#####""")
    s, g, hot = (1, 1), (3, 3), (2, 1)
    plain = astar(adj, s, g)
    assert hot in plain.path  # DOWN is listed before RIGHT, so the left route wins ties
    costly = astar(adj, s, g, cost_fn=lambda c: 10 if c == hot else 0)
    assert hot not in costly.path and len(costly.path) == 5 and costly.cost == 4
    blocked = astar(adj, s, g, blocked={(2, 1), (1, 2)})
    assert blocked.path == [] and blocked.cost == math.inf


def test_astar_trace_schema() -> None:
    adj = grid_from("""
#####
#...#
#####""")
    res = astar(adj, (1, 1), (1, 3), trace=True)
    t = res.trace
    assert t["type"] == "astar" and t["nodes"] == res.nodes_expanded == 3
    first = t["steps"][0]
    assert first == {"n": 1, "expand": [1, 1], "g": 0, "h": 2, "f": 2,
                     "open_size": 0, "open_top": []}
    assert t["steps"][1]["open_top"] == [] and t["path"] == [[1, 1], [1, 2], [1, 3]]
    assert all(s["f"] == s["g"] + s["h"] for s in t["steps"])
    assert greedy_best_first(adj, (1, 1), (1, 3), trace=True).trace["type"] == "greedy"
    assert astar(adj, (1, 1), (1, 3)).trace is None


def test_dls_found_cutoff_fail() -> None:
    adj = grid_from("""
#########
#.......#
#########
#.#######
#########""")
    goal = lambda c: c == (1, 7)  # noqa: E731
    assert dls(adj, (1, 1), goal, 6).status == FOUND
    assert dls(adj, (1, 1), goal, 6).path[-1] == (1, 7)
    cut = dls(adj, (1, 1), goal, 3)
    assert cut.status == CUTOFF and cut.cutoff_cells == [(1, 4)]
    # goal in another component: corridor fully explored within the limit
    assert dls(adj, (1, 1), lambda c: c == (3, 1), 10).status == FAIL
    # same but the limit is too small to see everything: cut off, not failure
    assert dls(adj, (1, 1), lambda c: c == (3, 1), 4).status == CUTOFF


def test_dls_safe_paths_hand_made() -> None:
    adj = grid_from("""
#######
#.....#
#.###.#
#.....#
#######""")
    start, tom = (1, 1), (1, 5)
    d_tom = bfs_distance_map(adj, tom)
    res = dls_safe_paths(adj, start, 3, d_tom)
    assert sorted(res.all_paths) == [
        [(1, 1), (1, 2), (1, 3), (1, 4)],
        [(1, 1), (2, 1), (3, 1), (3, 2)],
    ]
    # toward Tom: (1,4) at step 3 has d_tom 1 -> unsafe. Down the left side is safe.
    assert res.safe == [[(1, 1), (2, 1), (3, 1), (3, 2)]]
    for p in res.safe:
        assert all(d_tom[c] > t for t, c in enumerate(p) if t)
    assert res.cutoffs == 2 and res.dead_ends == 0
    dead = dls_safe_paths(grid_from("#####\n#...#\n#####"), (1, 1), 5, {})
    assert dead.all_paths == [] and dead.dead_ends == 1


def test_dead_end_cells_hand_made() -> None:
    adj = grid_from("""
#########
#.......#
#.#.###.#
#.#.....#
###.#####
#...#####
#########""")
    # (3,1) tip -> (2,1) -> (1,1) -> (1,2) -> (1,3) junction (3 nbrs). Stop there.
    # (5,1) tip -> (5,2) -> (5,3) -> (4,3) -> (3,3) junction.
    assert dead_end_cells(adj) == {(3, 1), (2, 1), (1, 1), (1, 2),
                                   (5, 1), (5, 2), (5, 3), (4, 3)}
    loop = grid_from("#####\n#...#\n#.#.#\n#...#\n#####")
    assert dead_end_cells(loop) == set()


def test_flood_fill_and_reachable() -> None:
    adj = grid_from("""
#######
#.....#
###.###
#.....#
#######""")
    assert flood_fill_count(adj, (1, 1)) == 11
    assert flood_fill_count(adj, (1, 1), blocked={(2, 3)}) == 5
    assert flood_fill_count(adj, (1, 1), blocked={(1, 1), (1, 2)}) == 1
    assert reachable(adj, (1, 1), (3, 5)) and not reachable(adj, (1, 1), (3, 5), {(2, 3)})
    m = generate_maze(7)
    assert flood_fill_count(m.adj, m.jerry_start) == len(m.floor)
    assert dfs(m.adj, m.jerry_start, trace=True).trace["type"] == "dfs"


def test_bidirectional_trace() -> None:
    m = generate_maze(11)
    res = bidirectional_bfs(m.adj, m.jerry_start, m.tom_start, trace=True)
    t = res.trace
    assert t["type"] == "bidir" and t["meeting"] == list(res.meeting)
    assert t["nodes"] == len(t["forward_order"]) + len(t["backward_order"])
