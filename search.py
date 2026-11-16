"""Graph search over the maze. Phase 1: plain BFS distances and bidirectional BFS.

Cells are (row, col) tuples. Every function takes an adjacency mapping
`adj[cell] -> neighbour cells` so it works on any maze, real or test-built.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

Cell = tuple[int, int]
Adjacency = Mapping[Cell, Sequence[Cell]]


def bfs_distances(adj: Adjacency, start: Cell, max_dist: int | None = None) -> dict[Cell, int]:
    """Breadth-first search distance map.

    What: BFS from `start`, returns {cell: number of steps}. Walls are simply
    absent from `adj`, so they block. Optional `max_dist` stops early.
    Where used: fog of war (vision = path distance <= 5), Bruno's shortest-path
    steps, maze placement rules (start/key distances).
    """
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        d = dist[cell]
        if max_dist is not None and d >= max_dist:
            continue
        for nxt in adj[cell]:
            if nxt not in dist:
                dist[nxt] = d + 1
                queue.append(nxt)
    return dist


@dataclass
class BidirResult:
    """Outcome of a bidirectional search. `path` is empty when no path exists."""

    path: list[Cell]
    meeting: Cell | None
    forward_order: list[Cell] = field(default_factory=list)
    backward_order: list[Cell] = field(default_factory=list)

    @property
    def nodes(self) -> int:
        """Total cells expanded by both searches."""
        return len(self.forward_order) + len(self.backward_order)


def _walk_back(parents: dict[Cell, Cell | None], cell: Cell) -> list[Cell]:
    """Follow parent links from `cell` to the search root; returns cell..root."""
    out = [cell]
    while (p := parents[out[-1]]) is not None:
        out.append(p)
    return out


def bidirectional_bfs(adj: Adjacency, start: Cell, goal: Cell) -> BidirResult:
    """Bidirectional breadth-first search.

    What: two BFS waves, one from `start` and one from `goal`. Each round expands
    one whole layer of the smaller frontier. When a layer touches cells already
    reached by the other wave, the best meeting cell of that layer (smallest
    d_forward + d_backward) joins both half paths into a shortest path.
    Why: each wave only reaches about half the depth, so far fewer cells are
    expanded than one BFS over the full distance.
    Where used: maze validation (every key/exit/kennel reachable from both starts);
    later Tom's AMBUSH mode.
    """
    if start == goal:
        return BidirResult(path=[start], meeting=start, forward_order=[start])
    par_f: dict[Cell, Cell | None] = {start: None}
    par_b: dict[Cell, Cell | None] = {goal: None}
    dist_f, dist_b = {start: 0}, {goal: 0}
    front_f, front_b = [start], [goal]
    result = BidirResult(path=[], meeting=None)
    while front_f and front_b:
        forward = len(front_f) <= len(front_b)
        front, par, dist, other = (
            (front_f, par_f, dist_f, dist_b) if forward else (front_b, par_b, dist_b, dist_f)
        )
        order = result.forward_order if forward else result.backward_order
        next_front: list[Cell] = []
        best: tuple[int, Cell] | None = None
        for cell in front:
            order.append(cell)
            for nxt in adj[cell]:
                if nxt not in par:
                    par[nxt] = cell
                    dist[nxt] = dist[cell] + 1
                    next_front.append(nxt)
                if nxt in other:
                    total = dist[nxt] + other[nxt]
                    if best is None or total < best[0]:
                        best = (total, nxt)
        if best is not None:
            meet = best[1]
            result.meeting = meet
            result.path = _walk_back(par_f, meet)[::-1] + _walk_back(par_b, meet)[1:]
            return result
        if forward:
            front_f = next_front
        else:
            front_b = next_front
    return result
