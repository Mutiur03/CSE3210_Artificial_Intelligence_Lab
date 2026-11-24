"""Graph search on the maze grid. Pure functions: no game rules, no pygame.

The grid is an adjacency mapping `grid[cell] -> neighbour floor cells` (a maze's
`adj`, or a small hand-built dict in tests). Walls are simply absent, so they
block. `blocked` is an optional set of extra cells that may not be entered.
Neighbours are visited in the order the grid lists them (UP, DOWN, LEFT, RIGHT
for real mazes), so every result is deterministic.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

Cell = tuple[int, int]
Grid = Mapping[Cell, Sequence[Cell]]



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




def bfs_distance_map(grid: Grid, source: Cell,
                     blocked: Collection[Cell] | None = None) -> dict[Cell, int]:
    """Breadth-first search distance map: {cell: steps from source}.

    What: FIFO queue from `source`; the first time a cell is reached is by a
    shortest path, so its distance is final. Unreachable cells are absent.
    Where used: fog of war (vision = distance <= 5), Bruno's shortest-path steps,
    the minimax evaluation's distances, maze placement rules (start/key distances).
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
    Where used: an MCTS Jerry's route to her target around a visible Tom, and
    the reference bidirectional BFS is tested against.
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
    starts).
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




def core_cells(grid: Grid) -> set[Cell]:
    """Cells with two ways out: the 2-core of the maze graph.

    What: repeatedly delete every cell that has at most one remaining
    neighbour (a dead-end tip) until none is left. A pocket of nested dead
    ends disappears completely; what remains lies on a loop or on a corridor
    between loops, so a character standing there can always run either way.
    Where used: key placement (maze._place) keeps keys out of dead-end
    pockets, where Tom could trap Jerry with no way out.
    """
    degree = {cell: len(nbrs) for cell, nbrs in grid.items()}
    stack = [cell for cell, d in degree.items() if d <= 1]
    gone: set[Cell] = set()
    while stack:
        cell = stack.pop()
        if cell in gone:
            continue
        gone.add(cell)
        for n in grid[cell]:
            if n not in gone:
                degree[n] -= 1
                if degree[n] <= 1:
                    stack.append(n)
    return set(grid) - gone


def dead_end_cells(grid: Grid) -> set[Cell]:
    """Cells in dead-end corridors.

    What: start at every cell with exactly one floor neighbour and walk back
    along the corridor (cells with exactly two neighbours) until a junction
    (3+ neighbours) is reached. Every cell walked, the tip included and the
    junction excluded, is a dead-end cell: entering it leads nowhere.
    Where used: the minimax evaluation (+5 for Jerry in one while Tom is near).
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
