"""Maze generation (DFS recursive backtracker), loop carving, feature placement, validation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import config as C
from search import Cell, bfs_distances, bidirectional_bfs

INF = 10**9


@dataclass(eq=False)
class Maze:
    """Static board: floor cells plus feature cells. Never changes during a game.

    `adj` lists floor neighbours in fixed order UP, DOWN, LEFT, RIGHT so every
    tie-break in the game is deterministic. BFS distance maps are cached per
    source cell because the walls never move.
    """

    rows: int
    cols: int
    floor: frozenset[Cell]
    keys: tuple[Cell, ...]
    exit: Cell
    kennel: Cell
    jerry_start: Cell
    tom_start: Cell
    seed: int = 0
    attempt: int = 0
    adj: dict[Cell, tuple[Cell, ...]] = field(init=False, repr=False)
    _dist_cache: dict[Cell, dict[Cell, int]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.adj = {cell: neighbours(self.floor, cell) for cell in self.floor}
        self._dist_cache = {}

    def is_floor(self, cell: Cell) -> bool:
        return cell in self.floor

    def dist_map(self, src: Cell) -> dict[Cell, int]:
        """BFS distance map from `src` (cached)."""
        if src not in self._dist_cache:
            self._dist_cache[src] = bfs_distances(self.adj, src)
        return self._dist_cache[src]

    def dist(self, a: Cell, b: Cell) -> int:
        """Path distance between two floor cells (INF if unreachable)."""
        return self.dist_map(a).get(b, INF)


def neighbours(floor: frozenset[Cell] | set[Cell], cell: Cell) -> tuple[Cell, ...]:
    """Floor cells next to `cell` in order UP, DOWN, LEFT, RIGHT."""
    r, c = cell
    out = []
    for dr, dc in (C.DELTAS[a] for a in ("UP", "DOWN", "LEFT", "RIGHT")):
        n = (r + dr, c + dc)
        if n in floor:
            out.append(n)
    return tuple(out)


def carve_dfs(size: int, rng: random.Random) -> set[Cell]:
    """DFS recursive backtracker (iterative stack version).

    What: cells sit at odd coordinates. Start at (1,1), mark it, push it. Look at
    unvisited cells two steps away; pick one at random, knock out the wall
    between, push it. If none is left, pop (backtrack). Ends when the stack is
    empty, giving a perfect maze (exactly one path between any two cells).
    Where used: building every game board.
    """
    start = (1, 1)
    floor = {start}
    stack = [start]
    while stack:
        r, c = stack[-1]
        options = [
            (r + dr, c + dc)
            for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2))
            if 0 < r + dr < size - 1 and 0 < c + dc < size - 1 and (r + dr, c + dc) not in floor
        ]
        if not options:
            stack.pop()
            continue
        nr, nc = rng.choice(options)
        floor.add(((r + nr) // 2, (c + nc) // 2))  # the wall between
        floor.add((nr, nc))
        stack.append((nr, nc))
    return floor


def add_loops(floor: set[Cell], size: int, rng: random.Random) -> int:
    """Remove LOOP_WALL_FRACTION of the removable interior walls; returns how many.

    A wall is removable when it sits strictly inside the border and separates two
    floor cells in a straight line (left/right or up/down). Removing it adds a loop.
    """
    candidates = []
    for r in range(1, size - 1):
        for c in range(1, size - 1):
            if (r, c) in floor:
                continue
            horiz = (r, c - 1) in floor and (r, c + 1) in floor
            vert = (r - 1, c) in floor and (r + 1, c) in floor
            if horiz != vert:  # exactly one straight passage through it
                candidates.append((r, c))
    count = round(C.LOOP_WALL_FRACTION * len(candidates))
    floor.update(rng.sample(candidates, count))
    return count


def _place(floor: frozenset[Cell], size: int, rng: random.Random) -> dict | None:
    """Try to place starts, keys, exit, kennel. Returns a dict or None on failure."""
    cells = sorted(floor)
    band = size // C.START_REGION_DIVISOR
    jerry_zone = [p for p in cells if p[0] < band and p[1] < band]
    tom_zone = [p for p in cells if p[0] >= size - band and p[1] >= size - band]
    adj = {cell: neighbours(floor, cell) for cell in floor}
    jerry, tom = rng.choice(jerry_zone), rng.choice(tom_zone)
    if bfs_distances(adj, jerry).get(tom, INF) < C.MIN_START_DISTANCE:
        return None
    pool = [p for p in cells if p not in (jerry, tom)]
    rng.shuffle(pool)
    keys: list[Cell] = []
    key_maps: list[dict[Cell, int]] = []
    for cand in pool:
        if all(m.get(cand, INF) >= C.MIN_KEY_SEPARATION for m in key_maps):
            keys.append(cand)
            key_maps.append(bfs_distances(adj, cand))
            if len(keys) == C.NUM_KEYS:
                break
    if len(keys) < C.NUM_KEYS:
        return None
    rest = [p for p in pool if p not in keys]
    exit_cell, kennel = rest[0], rest[1]
    return {"jerry": jerry, "tom": tom, "keys": tuple(keys), "exit": exit_cell, "kennel": kennel}


def validate(maze: Maze) -> bool:
    """Every key, exit and kennel reachable from both start cells (bidirectional BFS)."""
    targets = [*maze.keys, maze.exit, maze.kennel]
    return all(
        bidirectional_bfs(maze.adj, start, t).path
        for start in (maze.jerry_start, maze.tom_start)
        for t in targets
    )


def generate_maze(seed: int, size: int = C.DEFAULT_SIZE) -> Maze:
    """Build a valid board from `seed`. Same (seed, size) always gives the same maze.

    Attempt k uses rng seeded with the string "seed:size:k" (derived seed).
    Each attempt: DFS carve, add loops, place features, validate; any failure
    (placement rule or validation) moves on to the next derived seed.
    """
    if size % 2 == 0 or not C.MIN_SIZE <= size <= C.MAX_SIZE:
        raise ValueError(f"size must be odd and in {C.MIN_SIZE}..{C.MAX_SIZE}, got {size}")
    for attempt in range(C.MAX_MAZE_ATTEMPTS):
        rng = random.Random(f"{seed}:{size}:{attempt}")
        floor_set = carve_dfs(size, rng)
        add_loops(floor_set, size, rng)
        floor = frozenset(floor_set)
        spot = _place(floor, size, rng)
        if spot is None:
            continue
        maze = Maze(
            rows=size, cols=size, floor=floor, keys=spot["keys"], exit=spot["exit"],
            kennel=spot["kennel"], jerry_start=spot["jerry"], tom_start=spot["tom"],
            seed=seed, attempt=attempt,
        )
        if validate(maze):
            return maze
    raise RuntimeError(f"no valid maze for seed {seed} size {size}")
