"""Graph search on the maze grid. Pure functions: no game rules, no pygame.

The grid is an adjacency mapping `grid[cell] -> neighbour floor cells` (a maze's
`adj`, or a small hand-built dict in tests). Walls are simply absent, so they
block. `blocked` is an optional set of extra cells that may not be entered.
Neighbours are visited in the order the grid lists them (UP, DOWN, LEFT, RIGHT
for real mazes), so every result is deterministic.
"""

from __future__ import annotations

import heapq
import math
import time
from collections import deque
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

Cell = tuple[int, int]
Grid = Mapping[Cell, Sequence[Cell]]

FOUND, CUTOFF, FAIL = "FOUND", "CUTOFF", "FAIL"
OPEN_TOP = 5  # open-list entries recorded per A*/greedy trace step


@dataclass
class SearchResult:
    """Outcome of one search. `path` runs start..goal and is empty when none exists.

    `cost` is the summed entry cost of the path (steps for unit costs, inf if no
    path). `explored_order` lists expanded cells in order. `trace` follows
    CLAUDE.md 4.8 and is only built when the caller asks for it.
    """

    path: list[Cell]
    cost: float
    nodes_expanded: int
    ms: float
    explored_order: list[Cell]
    trace: dict | None = None


@dataclass
class BidirResult(SearchResult):
    """SearchResult plus the meeting cell and the two expansion orders."""

    meeting: Cell | None = None
    forward_order: list[Cell] = field(default_factory=list)
    backward_order: list[Cell] = field(default_factory=list)


@dataclass
class DLSResult:
    """Depth-limited search outcome.

    status FOUND: `path` reaches a goal within the limit.
    status CUTOFF: no goal found, but some branch was stopped by the limit
    (`cutoff_cells`), so a deeper search might still succeed.
    status FAIL: no goal and nothing was cut off: no goal is reachable at all.
    """

    status: str
    path: list[Cell]
    nodes_expanded: int
    cutoff_cells: list[Cell]
    explored_order: list[Cell]


@dataclass
class SafePaths:
    """All exact-depth paths from a start cell, split into safe and unsafe.

    `all_paths` = every simple path of exactly `depth` steps (paths_enumerated).
    `safe` = those where Jerry reaches every cell before the enemy can.
    `cutoffs` = full-depth paths that could have continued (stopped by the limit).
    `dead_ends` = branches that ended before the limit with no new cell to enter
    (a failure, not a cutoff).
    """

    all_paths: list[list[Cell]]
    safe: list[list[Cell]]
    cutoffs: int
    dead_ends: int


def manhattan(a: Cell, b: Cell) -> int:
    """|dr| + |dc|. Never more than the real path length on a 4-connected grid."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _walk_back(parents: Mapping[Cell, Cell | None], cell: Cell) -> list[Cell]:
    """Follow parent links from `cell` to the search root; returns cell..root."""
    out = [cell]
    while (p := parents[out[-1]]) is not None:
        out.append(p)
    return out


def _moves(grid: Grid, cell: Cell, blocked: Collection[Cell] | None) -> list[Cell]:
    """Neighbours of `cell` that are not blocked."""
    return [n for n in grid[cell] if not blocked or n not in blocked]


# ------------------------------------------------------------------ BFS family


def bfs_distance_map(grid: Grid, source: Cell,
                     blocked: Collection[Cell] | None = None) -> dict[Cell, int]:
    """Breadth-first search distance map: {cell: steps from source}.

    What: FIFO queue from `source`; the first time a cell is reached is by a
    shortest path, so its distance is final. Unreachable cells are absent.
    Where used: fog of war (vision = distance <= 5), Bruno's shortest-path steps,
    Jerry's d_tom risk map, maze placement rules (start/key distances).
    """
    dist = {source: 0}
    queue = deque([source])
    while queue:
        cell = queue.popleft()
        for nxt in _moves(grid, cell, blocked):
            if nxt not in dist:
                dist[nxt] = dist[cell] + 1
                queue.append(nxt)
    return dist


def bfs(grid: Grid, start: Cell, goal: Cell,
        blocked: Collection[Cell] | None = None) -> SearchResult:
    """Plain breadth-first search start -> goal (shortest path in steps).

    What: FIFO queue, parent links, stop when the goal is dequeued.
    Where used: the reference the other searches are tested and benchmarked
    against (A*, bidirectional and IDDFS must match its path length).
    """
    t0 = time.perf_counter()
    parents: dict[Cell, Cell | None] = {start: None}
    queue = deque([start])
    order: list[Cell] = []
    while queue:
        cell = queue.popleft()
        order.append(cell)
        if cell == goal:
            path = _walk_back(parents, goal)[::-1]
            return SearchResult(path, len(path) - 1, len(order), _ms(t0), order)
        for nxt in _moves(grid, cell, blocked):
            if nxt not in parents:
                parents[nxt] = cell
                queue.append(nxt)
    return SearchResult([], math.inf, len(order), _ms(t0), order)


def bidirectional_bfs(grid: Grid, start: Cell, goal: Cell,
                      blocked: Collection[Cell] | None = None,
                      trace: bool = False) -> BidirResult:
    """Bidirectional breadth-first search.

    What: two BFS waves, one from `start` and one from `goal`, take turns
    expanding one whole layer each (forward, backward, forward, ...). When a
    layer touches a cell the other wave already reached, the best meeting cell
    of that layer (smallest d_forward + d_backward) joins the two half paths into
    a shortest path. Each wave only goes about half the distance, so far fewer
    cells are expanded than with one BFS.
    Where used: maze validation (every key/exit/kennel reachable from both
    starts) and Tom's AMBUSH mode (meeting cell + path between Tom and target).
    """
    t0 = time.perf_counter()
    if start == goal:
        res = BidirResult([start], 0, 1, 0.0, [start], meeting=start, forward_order=[start])
    else:
        res = _bidir(grid, start, goal, blocked)
    res.ms = _ms(t0)
    if trace:
        res.trace = {"type": "bidir", "forward_order": [list(c) for c in res.forward_order],
                     "backward_order": [list(c) for c in res.backward_order],
                     "meeting": list(res.meeting) if res.meeting else None,
                     "path": [list(c) for c in res.path], "nodes": res.nodes_expanded}
    return res


def _bidir(grid: Grid, start: Cell, goal: Cell, blocked: Collection[Cell] | None) -> BidirResult:
    par_f: dict[Cell, Cell | None] = {start: None}
    par_b: dict[Cell, Cell | None] = {goal: None}
    dist_f, dist_b = {start: 0}, {goal: 0}
    front_f, front_b = [start], [goal]
    fwd_order: list[Cell] = []
    bwd_order: list[Cell] = []
    forward = True
    while front_f and front_b:
        front, par, dist, other, order = (
            (front_f, par_f, dist_f, dist_b, fwd_order) if forward
            else (front_b, par_b, dist_b, dist_f, bwd_order)
        )
        next_front: list[Cell] = []
        best: tuple[int, Cell] | None = None
        for cell in front:
            order.append(cell)
            for nxt in _moves(grid, cell, blocked):
                if nxt not in par:
                    par[nxt] = cell
                    dist[nxt] = dist[cell] + 1
                    next_front.append(nxt)
                if nxt in other and (best is None or dist[nxt] + other[nxt] < best[0]):
                    best = (dist[nxt] + other[nxt], nxt)
        if best is not None:
            meet = best[1]
            path = _walk_back(par_f, meet)[::-1] + _walk_back(par_b, meet)[1:]
            return BidirResult(path, len(path) - 1, len(fwd_order) + len(bwd_order), 0.0,
                               fwd_order + bwd_order, meeting=meet,
                               forward_order=fwd_order, backward_order=bwd_order)
        if forward:
            front_f = next_front
        else:
            front_b = next_front
        forward = not forward
    return BidirResult([], math.inf, len(fwd_order) + len(bwd_order), 0.0,
                       fwd_order + bwd_order, forward_order=fwd_order, backward_order=bwd_order)


def reachable(grid: Grid, a: Cell, b: Cell, blocked: Collection[Cell] | None = None) -> bool:
    """True if `b` can be reached from `a` (bidirectional BFS). Used by maze validation."""
    return bool(bidirectional_bfs(grid, a, b, blocked).path)


# ------------------------------------------------------------------ best-first family


def _best_first(grid: Grid, start: Cell, goal: Cell, use_g: bool,
                cost_fn: Callable[[Cell], float] | None,
                blocked: Collection[Cell] | None, trace: bool) -> SearchResult:
    """Shared loop of A* (f = g + h) and greedy best-first (f = h).

    Open list = heap of (f, h, insertion number, cell); the insertion number makes
    ties first-in-first-out and keeps results deterministic. A cell is expanded at
    most once (closed set); stale heap entries are skipped when popped.
    """
    t0 = time.perf_counter()
    g: dict[Cell, float] = {start: 0}
    parents: dict[Cell, Cell | None] = {start: None}
    h0 = manhattan(start, goal)
    heap: list[tuple[float, int, int, Cell]] = [(h0, h0, 0, start)]
    pushed = 1
    closed: set[Cell] = set()
    order: list[Cell] = []
    steps: list[dict] = []
    while heap:
        f, h, _, cell = heapq.heappop(heap)
        if cell in closed:
            continue
        closed.add(cell)
        order.append(cell)
        if trace:
            live = sorted(e for e in heap if e[3] not in closed)
            steps.append({"n": len(order), "expand": list(cell), "g": g[cell], "h": h, "f": f,
                          "open_size": len(live),
                          "open_top": [[list(e[3]), e[0]] for e in live[:OPEN_TOP]]})
        if cell == goal:
            break
        for nxt in _moves(grid, cell, blocked):
            if nxt in closed:
                continue
            new_g = g[cell] + 1 + (cost_fn(nxt) if cost_fn else 0)
            # A* re-opens a cell when it finds a cheaper route; greedy keeps the first one.
            if nxt not in g or (use_g and new_g < g[nxt]):
                g[nxt] = new_g
                parents[nxt] = cell
                nh = manhattan(nxt, goal)
                heapq.heappush(heap, (new_g + nh if use_g else nh, nh, pushed, nxt))
                pushed += 1
    found = goal in closed
    path = _walk_back(parents, goal)[::-1] if found else []
    res = SearchResult(path, g[goal] if found else math.inf, len(order), _ms(t0), order)
    if trace:
        res.trace = {"type": "astar" if use_g else "greedy", "start": list(start),
                     "goal": list(goal), "steps": steps, "path": [list(c) for c in path],
                     "nodes": len(order)}
    return res


def astar(grid: Grid, start: Cell, goal: Cell, cost_fn: Callable[[Cell], float] | None = None,
          blocked: Collection[Cell] | None = None, trace: bool = False) -> SearchResult:
    """A* search: expand the open cell with the smallest f = g + h.

    What: g = cost paid so far, h = Manhattan distance to the goal. Entering a
    cell costs 1 + cost_fn(cell) (cost_fn >= 0), so Manhattan never overestimates
    and the path found is the cheapest one.
    Where used: Tom HUNT (unit cost), Jerry SNEAK and DASH (cost_fn = danger
    near Tom + dead-end penalty), Jerry RUN_FOR_BRUNO; compared with greedy in
    the algorithm demo and experiments.
    """
    return _best_first(grid, start, goal, True, cost_fn, blocked, trace)


def greedy_best_first(grid: Grid, start: Cell, goal: Cell,
                      blocked: Collection[Cell] | None = None,
                      trace: bool = False) -> SearchResult:
    """Greedy best-first search: expand the open cell with the smallest h only.

    What: like A* but ignores the cost so far, so it rushes toward the goal. It
    always finds a path if one exists (closed set, finite grid) but the path may
    be longer than the shortest one.
    Where used: EASY Tom and EASY Jerry; compared with A* in the demo (`C` key)
    and in the benchmark.
    """
    return _best_first(grid, start, goal, False, None, blocked, trace)


# ------------------------------------------------------------------ depth-first family


def dfs(grid: Grid, start: Cell, goal: Cell | None = None,
        blocked: Collection[Cell] | None = None, trace: bool = False) -> SearchResult:
    """Iterative depth-first search with an explicit stack and a visited set.

    What: pop the newest cell, mark it visited, push its unvisited neighbours
    (reversed, so the first-listed neighbour is explored first). Stops when the
    goal is popped; with no goal it visits the whole reachable region. The path
    follows parent links, so it is *a* path, usually not the shortest.
    Where used: Tom SWEEP (visit unseen cells in DFS order); the maze itself is
    carved by the same idea (maze.carve_dfs).
    """
    t0 = time.perf_counter()
    parents: dict[Cell, Cell | None] = {start: None}
    stack = [start]
    visited: set[Cell] = set()
    order: list[Cell] = []
    while stack:
        cell = stack.pop()
        if cell in visited:
            continue
        visited.add(cell)
        order.append(cell)
        if cell == goal:
            break
        for nxt in reversed(_moves(grid, cell, blocked)):
            if nxt not in visited:
                parents[nxt] = cell
                stack.append(nxt)
    path = _walk_back(parents, goal)[::-1] if goal is not None and goal in visited else []
    res = SearchResult(path, len(path) - 1 if path else math.inf, len(order), _ms(t0), order)
    if trace:
        res.trace = {"type": "dfs", "order": [list(c) for c in order],
                     "path": [list(c) for c in path]}
    return res


def flood_fill_count(grid: Grid, start: Cell, blocked: Collection[Cell] | None = None) -> int:
    """Number of cells reachable from `start` without entering `blocked` (DFS).

    `start` itself is always counted, even if it is in `blocked`.
    Where used: Jerry EVADE scores the end of each DLS path by how much room is
    left (blocked = the path), and the minimax evaluation's escape room.
    """
    return dfs(grid, start, None, blocked).nodes_expanded


def dead_end_cells(grid: Grid) -> set[Cell]:
    """Cells in dead-end corridors.

    What: start at every cell with exactly one floor neighbour and walk back
    along the corridor (cells with exactly two neighbours) until a junction
    (3+ neighbours) is reached. Every cell walked, the tip included and the
    junction excluded, is a dead-end cell: entering it leads nowhere.
    Where used: Jerry's A* adds +3 cost on these cells when Tom is near, EVADE
    subtracts 5 for paths ending in one, minimax evaluation +5 for Jerry in one.
    """
    out: set[Cell] = set()
    for tip, nbrs in grid.items():
        if len(nbrs) != 1:
            continue
        prev, cell = None, tip
        while cell not in out and len(grid[cell]) <= 2:
            out.add(cell)
            nxt = [n for n in grid[cell] if n != prev]
            if not nxt:
                break
            prev, cell = cell, nxt[0]
    return out


def dls(grid: Grid, start: Cell, goal_test: Callable[[Cell], bool],
        depth_limit: int) -> DLSResult:
    """Depth-limited search (recursive depth-first search that stops at a depth).

    What: DFS that never goes deeper than `depth_limit` steps. A cell is
    re-entered only along a strictly shorter route than before (best-depth
    table), so loops in the maze cannot blow up the search. Returns:
      FOUND  - a goal cell was reached; `path` leads to it,
      CUTOFF - no goal, but some cell at the limit still had unexplored
               neighbours (`cutoff_cells`): a deeper limit might succeed,
      FAIL   - no goal and nothing cut off: no goal is reachable at any depth.
    Where used: core of IDDFS (benchmark); Jerry EVADE uses the exact-depth
    variant `dls_safe_paths`.
    """
    best_depth: dict[Cell, int] = {}
    order: list[Cell] = []
    cutoffs: list[Cell] = []

    def recurse(cell: Cell, depth: int, path: list[Cell]) -> list[Cell] | None:
        best_depth[cell] = depth
        order.append(cell)
        if goal_test(cell):
            return path
        if depth == depth_limit:
            if any(n not in best_depth for n in grid[cell]):
                cutoffs.append(cell)
            return None
        for nxt in grid[cell]:
            if best_depth.get(nxt, math.inf) > depth + 1:
                found = recurse(nxt, depth + 1, path + [nxt])
                if found:
                    return found
        return None

    path = recurse(start, 0, [start])
    status = FOUND if path else (CUTOFF if cutoffs else FAIL)
    return DLSResult(status, path or [], len(order), cutoffs, order)


def iddfs(grid: Grid, start: Cell, goal: Cell) -> SearchResult:
    """Iterative deepening DFS: run DLS with limit 0, 1, 2, ... until FOUND or FAIL.

    What: DFS memory use with BFS's guarantee of a shortest path, at the price
    of re-expanding the shallow cells on every iteration.
    Where used: bonus, shown in the search benchmark only.
    """
    t0 = time.perf_counter()
    nodes = 0
    order: list[Cell] = []
    limit = 0
    while True:
        res = dls(grid, start, lambda c: c == goal, limit)
        nodes += res.nodes_expanded
        order = res.explored_order
        if res.status != CUTOFF:
            cost = len(res.path) - 1 if res.path else math.inf
            return SearchResult(res.path, cost, nodes, _ms(t0), order)
        limit += 1


def dls_safe_paths(grid: Grid, start: Cell, depth: int, d_enemy: Mapping[Cell, int]) -> SafePaths:
    """Enumerate every simple path of exactly `depth` steps and keep the safe ones.

    What: depth-limited DFS from `start` that never revisits a cell on the
    current path. A path c0..c_depth is SAFE if for every step t >= 1 the enemy's
    distance d_enemy[c_t] > t, i.e. Jerry is there before the enemy could be
    (cells the enemy cannot reach count as infinitely far).
    Where used: Jerry EVADE (depth 5, d_enemy = BFS distance map from Tom).
    """
    all_paths: list[list[Cell]] = []
    cutoffs = dead_ends = 0

    def extend(path: list[Cell]) -> None:
        nonlocal cutoffs, dead_ends
        nxts = [n for n in grid[path[-1]] if n not in path]
        if len(path) - 1 == depth:
            all_paths.append(path)
            cutoffs += bool(nxts)
            return
        if not nxts:
            dead_ends += 1
        for n in nxts:
            extend(path + [n])

    extend([start])
    safe = [p for p in all_paths
            if all(d_enemy.get(c, math.inf) > t for t, c in enumerate(p) if t >= 1)]
    return SafePaths(all_paths, safe, cutoffs, dead_ends)
