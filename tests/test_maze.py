import time

import pytest

import config as C
from maze import INF, generate_maze, validate
from search import bfs_distance_map, bidirectional_bfs


def check_rules(m) -> None:
    n = m.rows
    assert n % 2 == 1
    border = {(r, c) for r in range(n) for c in range(n) if r in (0, n - 1) or c in (0, n - 1)}
    assert not border & m.floor, "outer border must stay wall"
    assert m.dist(m.jerry_start, m.tom_start) >= C.MIN_START_DISTANCE
    assert m.jerry_start in m.floor and m.tom_start in m.floor
    assert len(m.keys) == C.NUM_KEYS
    for i, a in enumerate(m.keys):
        assert a not in (m.jerry_start, m.tom_start)
        for b in m.keys[i + 1:]:
            assert m.dist(a, b) >= C.MIN_KEY_SEPARATION
    specials = [*m.keys, m.exit, m.kennel, m.jerry_start, m.tom_start]
    assert len(set(specials)) == len(specials)
    for t in [*m.keys, m.exit, m.kennel]:
        assert m.dist(m.jerry_start, t) < INF and m.dist(m.tom_start, t) < INF
    assert validate(m)


def test_200_seeds_valid_and_fast() -> None:
    t0 = time.perf_counter()
    mazes = [generate_maze(seed, 21) for seed in range(200)]
    elapsed = time.perf_counter() - t0
    for m in mazes:
        check_rules(m)
    assert elapsed < 20, f"200 mazes took {elapsed:.1f}s"


@pytest.mark.parametrize("size", C.MAP_SIZES)
def test_all_sizes(size: int) -> None:
    for seed in range(10):
        check_rules(generate_maze(seed, size))


def test_same_seed_same_maze() -> None:
    a, b = generate_maze(42), generate_maze(42)
    assert (a.floor, a.keys, a.exit, a.kennel, a.jerry_start, a.tom_start) == (
        b.floor, b.keys, b.exit, b.kennel, b.jerry_start, b.tom_start)
    assert generate_maze(43).floor != a.floor


def test_bad_size_rejected() -> None:
    for size in (20, 13, 33):
        with pytest.raises(ValueError):
            generate_maze(1, size)


def test_has_loops() -> None:
    """A perfect maze is a tree (edges = cells - 1); loops add extra edges."""
    m = generate_maze(3)
    edges = sum(len(v) for v in m.adj.values()) // 2
    assert edges > len(m.floor) - 1


def test_bidirectional_matches_bfs() -> None:
    m = generate_maze(5)
    cells = sorted(m.floor)
    for goal in cells[::7]:
        res = bidirectional_bfs(m.adj, m.jerry_start, goal)
        assert res.path[0] == m.jerry_start and res.path[-1] == goal
        assert len(res.path) - 1 == bfs_distance_map(m.adj, m.jerry_start)[goal]
        assert all(b in m.adj[a] for a, b in zip(res.path, res.path[1:], strict=False))
        assert res.meeting in res.path


def test_bidirectional_no_path() -> None:
    adj = {(0, 0): ((0, 1),), (0, 1): ((0, 0),), (5, 5): ()}
    res = bidirectional_bfs(adj, (0, 0), (5, 5))
    assert res.path == [] and res.meeting is None
