"""Game rules: state, actions, Bruno FSM, fog-of-war observations, win checks.

No pygame here. Round order (CLAUDE.md 3.2): Jerry acts, Tom acts (skipped while
stunned), Bruno acts, end-of-round timers, turn += 1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import config as C
from maze import Maze
from search import Cell

JERRY = "JERRY"
TOM = "TOM"
ROLES = (JERRY, TOM)
SLEEP, GUARD, CHASE_CAT, TIRED = "SLEEP", "GUARD", "CHASE_CAT", "TIRED"
BRUNO_STATES = (SLEEP, GUARD, CHASE_CAT, TIRED)
TRAP, WHISTLE = "TRAP", "WHISTLE"  # Jerry's gadgets (use_gadget)


@dataclass(frozen=True)
class Event:
    """Something that happened. `audience` = roles that learn about it."""

    turn: int
    text: str
    audience: frozenset[str]


@dataclass
class Bruno:
    """The bodyguard dog. Scripted finite-state machine, see bruno_step()."""

    pos: Cell
    state: str = SLEEP
    guard_timer: int = 0
    tired_timer: int = 0
    bite_cooldown: int = 0
    activations: int = 0


@dataclass
class GameState:
    """Full (omniscient) game state. Agents never see this, only Observation."""

    maze: Maze
    jerry: Cell
    tom: Cell
    keys: tuple[Cell, ...]  # keys still on the board
    bruno: Bruno | None
    exit: Cell | None = None  # exit cell as the simulating side knows it (None = unknown)
    keys_taken: int = 0
    exit_open: bool = False
    tom_stun: int = 0
    turn: int = 1
    winner: str | None = None
    reason: str = ""
    bites: int = 0
    traps: tuple[Cell, ...] = ()  # mouse traps on the floor (set by human Jerry only)
    traps_left: int = C.TRAP_LIMIT
    whistle_cd: int = 0  # turns until Jerry may whistle for Bruno again
    last_seen: dict[str, tuple[Cell, int] | None] = field(
        default_factory=lambda: {JERRY: None, TOM: None}
    )
    events: list[Event] = field(default_factory=list)
    action_log: list[tuple[int, str, str]] = field(default_factory=list)

    def copy(self, history: bool = True) -> GameState:
        """Fast copy. `history=False` starts empty event/action logs (for search trees)."""
        b = self.bruno
        return GameState(
            maze=self.maze, jerry=self.jerry, tom=self.tom, keys=self.keys,
            bruno=None if b is None else Bruno(
                b.pos, b.state, b.guard_timer, b.tired_timer, b.bite_cooldown, b.activations
            ),
            exit=self.exit,
            keys_taken=self.keys_taken, exit_open=self.exit_open, tom_stun=self.tom_stun,
            turn=self.turn, winner=self.winner, reason=self.reason, bites=self.bites,
            traps=self.traps, traps_left=self.traps_left, whistle_cd=self.whistle_cd,
            last_seen=dict(self.last_seen),
            events=list(self.events) if history else [],
            action_log=list(self.action_log) if history else [],
        )


@dataclass(frozen=True)
class Observation:
    """What one role may know this turn (CLAUDE.md 3.6). Walls (`maze`) are public."""

    role: str
    turn: int
    self_pos: Cell
    self_stun: int
    keys_taken: int
    key_cells: frozenset[Cell]
    exit_cell: Cell | None
    exit_open: bool
    kennel: Cell
    opp_pos: Cell | None
    opp_last_seen: tuple[Cell, int] | None
    opp_stun: int | None
    bruno: tuple[Cell, str] | None
    visible_cells: frozenset[Cell]
    events: tuple[str, ...]
    maze: Maze


# ------------------------------------------------------------------ setup


def new_game(maze: Maze, bruno_enabled: bool = True) -> GameState:
    """Fresh game on `maze`: Bruno asleep in the kennel, all keys on the board."""
    state = GameState(
        maze=maze, jerry=maze.jerry_start, tom=maze.tom_start, keys=tuple(maze.keys),
        bruno=Bruno(maze.kennel) if bruno_enabled else None, exit=maze.exit,
    )
    _update_sightings(state)
    return state


def other(role: str) -> str:
    return TOM if role == JERRY else JERRY


def pos_of(state: GameState, role: str) -> Cell:
    return state.jerry if role == JERRY else state.tom


def moves_from(maze: Maze, cell: Cell) -> list[str]:
    """Actions that keep you on the floor from `cell` (WAIT always included)."""
    r, c = cell
    return [a for a in C.ACTIONS if (r + C.DELTAS[a][0], c + C.DELTAS[a][1]) in maze.floor]


def step(cell: Cell, action: str) -> Cell:
    dr, dc = C.DELTAS[action]
    return (cell[0] + dr, cell[1] + dc)


def direction(src: Cell, dst: Cell) -> str:
    """Action that moves from `src` to the adjacent cell `dst` (WAIT if they are equal)."""
    for a in C.ACTIONS:
        if step(src, a) == dst:
            return a
    raise ValueError(f"{dst} is not next to {src}")


def legal_actions(state: GameState, role: str) -> list[str]:
    """Legal actions for `role`. A stunned Tom may only WAIT (his move is skipped)."""
    if state.winner is not None:
        return []
    if role == TOM and state.tom_stun > 0:
        return ["WAIT"]
    return moves_from(state.maze, pos_of(state, role))


# ------------------------------------------------------------------ helpers


def _witnesses(state: GameState, cell: Cell, *always: str) -> frozenset[str]:
    """Roles that can see `cell` (path distance <= vision), plus `always`."""
    seen = {r for r in ROLES if state.maze.dist(pos_of(state, r), cell) <= C.VISION_RADIUS}
    return frozenset(seen | set(always))


def _emit(state: GameState, out: list[Event], text: str, audience: frozenset[str]) -> None:
    ev = Event(state.turn, text, audience)
    out.append(ev)
    state.events.append(ev)


def _win(state: GameState, out: list[Event], winner: str, reason: str) -> None:
    state.winner, state.reason = winner, reason
    _emit(state, out, reason, frozenset(ROLES))


def _update_sightings(state: GameState) -> None:
    """If Tom and Jerry are within vision of each other, both remember it now."""
    if state.maze.dist(state.jerry, state.tom) <= C.VISION_RADIUS:
        state.last_seen[JERRY] = (state.tom, state.turn)
        state.last_seen[TOM] = (state.jerry, state.turn)


def toward(maze: Maze, src: Cell, goal: Cell) -> Cell:
    """Next cell on a BFS shortest path src -> goal (first in UP/DOWN/LEFT/RIGHT order).

    Used by Bruno's FSM and by the cheap MCTS playout policies.
    """
    if src == goal:
        return src
    dmap = maze.dist_map(goal)
    return next(n for n in maze.adj[src] if dmap[n] == dmap[src] - 1)


# ------------------------------------------------------------------ actions


def apply_action(state: GameState, role: str, action: str) -> list[Event]:
    """Apply one action for `role`, check wins, return the events it caused."""
    if action not in legal_actions(state, role):
        raise ValueError(f"illegal action {action} for {role} at turn {state.turn}")
    state.action_log.append((state.turn, role, action))
    out: list[Event] = []
    if role == TOM and state.tom_stun > 0:
        state.tom_stun -= 1
        _emit(state, out, "Tom is stunned and skips his move", _witnesses(state, state.tom, TOM))
        return out
    new = step(pos_of(state, role), action)
    if role == JERRY:
        state.jerry = new
        if new == state.tom and not (state.exit_open and new == state.exit):  # exit beats capture
            _win(state, out, TOM, "Jerry ran into Tom")
            return out
        _jerry_lands(state, out)
    else:
        state.tom = new
        if new == state.jerry:
            _win(state, out, TOM, "Tom caught Jerry")
            return out
        if new in state.traps:
            state.traps = tuple(t for t in state.traps if t != new)
            state.tom_stun = C.TRAP_STUN
            _emit(state, out, f"Tom springs a mouse trap! Stunned {C.TRAP_STUN} turns",
                  frozenset(ROLES))
    _update_sightings(state)
    return out


def gadget_ready(state: GameState, kind: str) -> bool:
    """Can Jerry use `kind` ("TRAP" or "WHISTLE") this turn? See use_gadget()."""
    if state.winner is not None:
        return False
    b = state.bruno
    if kind == TRAP:
        return (
            state.traps_left > 0 and state.jerry not in state.traps
            and state.jerry != state.maze.exit
        )
    if kind == WHISTLE:
        return (
            state.whistle_cd == 0 and b is not None and b.state in (GUARD, TIRED)
            and state.maze.dist(state.jerry, b.pos) <= C.VISION_RADIUS
        )
    raise ValueError(f"unknown gadget {kind}")


def use_gadget(state: GameState, kind: str) -> list[Event]:
    """Jerry spends her turn on a gadget instead of moving (Tom then acts as usual).

    TRAP: a mouse trap on Jerry's cell; it springs when Tom steps on it (stun, then
    removed). Tom's AI does not know traps, so it walks into them like any cell.
    WHISTLE: Bruno, if he is guarding or walking home within vision, goes back to
    GUARD with a fresh guard timer (no teleport, he still walks). Free of the two
    wake-up activations.
    """
    if not gadget_ready(state, kind):
        raise ValueError(f"gadget {kind} not ready for Jerry at turn {state.turn}")
    state.action_log.append((state.turn, JERRY, kind))
    out: list[Event] = []
    if kind == TRAP:
        state.traps += (state.jerry,)
        state.traps_left -= 1
        _emit(state, out, f"You set a mouse trap ({state.traps_left} left)", frozenset({JERRY}))
    else:
        b = state.bruno
        assert b is not None
        b.state, b.guard_timer = GUARD, C.BRUNO_GUARD_TURNS
        state.whistle_cd = C.WHISTLE_COOLDOWN
        _emit(state, out, "You whistle: Bruno comes back to guard you", frozenset({JERRY}))
    return out


def _jerry_lands(state: GameState, out: list[Event]) -> None:
    """Key pickup, alarm, exit, kennel wake-up after Jerry's action."""
    cell = state.jerry
    if cell in state.keys:
        state.keys = tuple(k for k in state.keys if k != cell)
        state.keys_taken += 1
        _emit(state, out, f"Jerry took a key ({state.keys_taken}/{C.NUM_KEYS})", frozenset(ROLES))
        if state.keys_taken == C.NUM_KEYS:
            state.exit_open = True
            _emit(state, out, f"ALARM! Exit open at {state.exit}", frozenset(ROLES))
    if state.exit_open and cell == state.exit:
        _win(state, out, JERRY, "Jerry escaped through the exit")
        return
    b = state.bruno
    if (
        b is not None and cell == state.maze.kennel and b.state == SLEEP
        and b.activations < C.BRUNO_MAX_ACTIVATIONS
    ):
        b.state, b.guard_timer = GUARD, C.BRUNO_GUARD_TURNS
        b.activations += 1
        _emit(state, out, f"Bruno wakes up and guards Jerry ({b.activations}/2)",
              _witnesses(state, b.pos, JERRY))


# ------------------------------------------------------------------ Bruno FSM


def bruno_step(state: GameState) -> list[Event]:
    """Bruno's move for this round (finite-state machine, CLAUDE.md 3.5).

    SLEEP: stays in the kennel. GUARD: follows Jerry (stays within 2); switches to
    CHASE_CAT if an unstunned Tom is within path distance 3. CHASE_CAT: steps
    toward Tom, bites when adjacent and cooldown is 0 (Tom stun 3), gives up when
    Tom is farther than 5. TIRED: walks back to the kennel.
    """
    b, out = state.bruno, []
    if b is None or state.winner is not None:
        return out
    maze = state.maze
    if b.state == GUARD and state.tom_stun == 0 and (
        maze.dist(b.pos, state.tom) <= C.BRUNO_CHASE_TRIGGER_DIST
    ):
        b.state = CHASE_CAT
        _emit(state, out, "Bruno chases Tom!", _witnesses(state, b.pos))
    if b.state == CHASE_CAT:
        if maze.dist(b.pos, state.tom) > C.BRUNO_BITE_RANGE:
            b.pos = toward(maze, b.pos, state.tom)
        d = maze.dist(b.pos, state.tom)
        if d <= C.BRUNO_BITE_RANGE and b.bite_cooldown == 0:
            state.tom_stun = C.BRUNO_BITE_STUN
            b.bite_cooldown = C.BRUNO_BITE_COOLDOWN
            b.state = GUARD
            state.bites += 1
            _emit(state, out, "Bruno bites Tom! Tom stunned 3 turns", _witnesses(state, b.pos, TOM))
        elif d > C.BRUNO_CHASE_GIVEUP_DIST:
            b.state = GUARD
            _emit(state, out, "Bruno lost Tom and returns to Jerry", _witnesses(state, b.pos))
    elif b.state == GUARD:
        if maze.dist(b.pos, state.jerry) > C.BRUNO_GUARD_FOLLOW_DIST:
            b.pos = toward(maze, b.pos, state.jerry)
    elif b.state == TIRED:
        b.pos = toward(maze, b.pos, maze.kennel)
    return out


def _tick_bruno(state: GameState, out: list[Event]) -> None:
    """End-of-round Bruno timers: cooldown, guard -> TIRED, TIRED -> SLEEP at kennel."""
    b = state.bruno
    if b is None:
        return
    b.bite_cooldown = max(0, b.bite_cooldown - 1)
    if b.state in (GUARD, CHASE_CAT):
        b.guard_timer -= 1
        if b.guard_timer <= 0:
            b.state, b.guard_timer, b.tired_timer = TIRED, 0, C.BRUNO_TIRED_TURNS
            _emit(state, out, "Bruno is tired and heads home", _witnesses(state, b.pos, JERRY))
    elif b.state == TIRED:
        b.tired_timer = max(0, b.tired_timer - 1)
        if b.tired_timer == 0 and b.pos == state.maze.kennel:
            b.state = SLEEP
            _emit(state, out, "Bruno fell asleep in the kennel", _witnesses(state, b.pos))


def _scent(state: GameState, out: list[Event]) -> None:
    """Pressure from turn SCENT_START_TURN: every SCENT_PERIOD turns Tom smells Jerry.

    Tom's memory of her cell is refreshed (he may then hunt it), so a Jerry who
    hides for a long time is found. Deterministic: no randomness.
    """
    since = state.turn - C.SCENT_START_TURN
    if since < 0 or since % C.SCENT_PERIOD != 0:
        return
    state.last_seen[TOM] = (state.jerry, state.turn)
    _emit(state, out, f"Tom sniffs you out at {state.jerry}", frozenset({TOM}))
    _emit(state, out, "Tom is onto your scent!", frozenset({JERRY}))


def end_of_round(state: GameState) -> list[Event]:
    """Bruno acts, timers tick, scent pulse, turn advances, turn limit checked."""
    out: list[Event] = []
    if state.winner is not None:
        return out
    out += bruno_step(state)
    _tick_bruno(state, out)
    state.whistle_cd = max(0, state.whistle_cd - 1)
    state.turn += 1
    _scent(state, out)
    if state.turn > C.TURN_LIMIT:
        _win(state, out, TOM, f"Time is up ({C.TURN_LIMIT} turns)")
    return out


Policy = Callable[[Observation], str]


def run_round(state: GameState, jerry: Policy, tom: Policy) -> list[Event]:
    """Play one full round. Policies receive only their own Observation."""
    out = apply_action(state, JERRY, jerry(make_observation(state, JERRY)))
    if state.winner is None:
        tom_action = "WAIT" if state.tom_stun > 0 else tom(make_observation(state, TOM))
        out += apply_action(state, TOM, tom_action)
    out += end_of_round(state)
    return out


# ------------------------------------------------------------------ observation


def make_observation(state: GameState, role: str) -> Observation:
    """Fog-of-war view for `role`: vision = BFS path distance <= 5 (walls block)."""
    maze = state.maze
    me, opp = pos_of(state, role), pos_of(state, other(role))
    visible = frozenset(c for c, d in maze.dist_map(me).items() if d <= C.VISION_RADIUS)
    opp_seen = opp in visible
    b = state.bruno
    since = state.turn - C.EVENT_MEMORY_ROUNDS
    return Observation(
        role=role,
        turn=state.turn,
        self_pos=me,
        self_stun=state.tom_stun if role == TOM else 0,
        keys_taken=state.keys_taken,
        key_cells=frozenset(state.keys),
        exit_cell=maze.exit if role == JERRY or state.exit_open else None,
        exit_open=state.exit_open,
        kennel=maze.kennel,
        opp_pos=opp if opp_seen else None,
        opp_last_seen=state.last_seen[role],
        opp_stun=(state.tom_stun if role == JERRY else 0) if opp_seen else None,
        bruno=(b.pos, b.state) if b is not None and b.pos in visible else None,
        visible_cells=visible,
        events=tuple(e.text for e in state.events if e.turn >= since and role in e.audience),
        maze=maze.public,
    )


def belief_state(obs: Observation, opp_pos: Cell, bruno_activations: int = 0) -> GameState:
    """A GameState built ONLY from `obs` (plus the agent's guess `opp_pos`).

    Minimax and MCTS simulate on this local copy, never on the real state.
    The opponent stands at `opp_pos`; Bruno exists only if visible (timers
    unknown: assumed full); an exit the role does not know stays None, so a
    simulated Jerry cannot escape through a cell Tom has not been told about.
    """
    jerry, tom = (obs.self_pos, opp_pos) if obs.role == JERRY else (opp_pos, obs.self_pos)
    bruno = None
    if obs.bruno is not None:
        pos, st = obs.bruno
        bruno = Bruno(pos, st, guard_timer=C.BRUNO_GUARD_TURNS if st in (GUARD, CHASE_CAT) else 0,
                      tired_timer=C.BRUNO_TIRED_TURNS if st == TIRED else 0,
                      activations=bruno_activations)
    return GameState(
        maze=obs.maze, jerry=jerry, tom=tom, keys=tuple(sorted(obs.key_cells)), bruno=bruno,
        exit=obs.exit_cell, keys_taken=obs.keys_taken, exit_open=obs.exit_open,
        tom_stun=obs.self_stun if obs.role == TOM else (obs.opp_stun or 0), turn=obs.turn,
    )


# ------------------------------------------------------------------ ASCII tools


_OVERRIDES = {
    "keys_taken", "exit_open", "bruno", "bruno_state", "guard_timer", "tired_timer",
    "bite_cooldown", "activations", "stun", "turn",
}


def from_ascii(text: str, **overrides: object) -> GameState:
    """Build a state from an ASCII map (for tests and the scenario).

    Legend: # wall, . floor, J Jerry, T Tom, B Bruno, K key, E exit, H kennel.
    Every letter stands on floor. Without B, Bruno sleeps on H; without H, the
    kennel is under B. keys_taken defaults to 3 - number of K.
    Overrides: keys_taken, exit_open, bruno (False = no Bruno), bruno_state,
    guard_timer, tired_timer, bite_cooldown, activations, stun (Tom), turn.
    """
    unknown = set(overrides) - _OVERRIDES
    if unknown:
        raise TypeError(f"unknown overrides: {sorted(unknown)}")
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len({len(ln) for ln in lines}) != 1:
        raise ValueError("ASCII map rows must have equal length")
    marks: dict[str, list[Cell]] = {}
    floor = set()
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            if ch not in "#.JTBKEH":
                raise ValueError(f"bad map char {ch!r} at {(r, c)}")
            if ch != "#":
                floor.add((r, c))
                marks.setdefault(ch, []).append((r, c))
    for need in "JTE":
        if len(marks.get(need, [])) != 1:
            raise ValueError(f"map needs exactly one {need}")
    bruno_cell = marks.get("B", [None])[0]
    kennel = marks.get("H", [bruno_cell])[0]
    if kennel is None:
        raise ValueError("map needs a kennel H (or Bruno B)")
    keys = tuple(marks.get("K", []))
    maze = Maze(
        rows=len(lines), cols=len(lines[0]), floor=frozenset(floor), keys=keys,
        exit=marks["E"][0], kennel=kennel, jerry_start=marks["J"][0], tom_start=marks["T"][0],
    )
    state = new_game(maze, bruno_enabled=bool(overrides.get("bruno", True)))
    state.keys_taken = int(overrides.get("keys_taken", C.NUM_KEYS - len(keys)))
    state.exit_open = bool(overrides.get("exit_open", state.keys_taken >= C.NUM_KEYS))
    state.tom_stun = int(overrides.get("stun", 0))
    state.turn = int(overrides.get("turn", 1))
    if state.bruno is not None:
        b = state.bruno
        b.pos = bruno_cell or kennel
        b.state = str(overrides.get("bruno_state", SLEEP if b.pos == kennel else GUARD))
        default_guard = C.BRUNO_GUARD_TURNS if b.state in (GUARD, CHASE_CAT) else 0
        b.guard_timer = int(overrides.get("guard_timer", default_guard))
        b.tired_timer = int(overrides.get("tired_timer", 0))
        b.bite_cooldown = int(overrides.get("bite_cooldown", 0))
        b.activations = int(overrides.get("activations", 0 if b.state == SLEEP else 1))
    state.last_seen = {JERRY: None, TOM: None}
    _update_sightings(state)
    return state


def render_ascii(state: GameState) -> str:
    """Text picture of the state, same legend as from_ascii (J > T > B > K > E > H)."""
    maze, b = state.maze, state.bruno
    rows = []
    for r in range(maze.rows):
        row = []
        for c in range(maze.cols):
            p = (r, c)
            if p == state.jerry:
                ch = "J"
            elif p == state.tom:
                ch = "T"
            elif b is not None and p == b.pos:
                ch = "B"
            elif p in state.keys:
                ch = "K"
            elif p == maze.exit:
                ch = "E"
            elif p == maze.kennel:
                ch = "H"
            else:
                ch = "." if p in maze.floor else "#"
            row.append(ch)
        rows.append("".join(row))
    return "\n".join(rows)


def invariant_errors(state: GameState) -> list[str]:
    """Sanity checks used by tests and the random-game script. Empty list = OK."""
    errs = []
    floor = state.maze.floor
    if state.jerry not in floor or state.tom not in floor:
        errs.append("character off the floor")
    if state.keys_taken + len(state.keys) != C.NUM_KEYS:
        errs.append("key count mismatch")
    if state.exit_open != (state.keys_taken >= C.NUM_KEYS):
        errs.append("exit_open does not match keys_taken")
    if state.tom_stun < 0 or state.tom_stun > C.BRUNO_BITE_STUN:
        errs.append("bad stun")
    if state.turn > C.TURN_LIMIT + 1 or (state.turn > C.TURN_LIMIT and state.winner is None):
        errs.append("turn limit passed without a winner")
    if state.winner is None and state.jerry == state.tom:
        errs.append("same cell but no winner")
    b = state.bruno
    if b is not None:
        if b.pos not in floor or b.state not in BRUNO_STATES:
            errs.append("bad Bruno")
        if b.state == SLEEP and b.pos != state.maze.kennel:
            errs.append("Bruno asleep outside kennel")
        if not 0 <= b.activations <= C.BRUNO_MAX_ACTIVATIONS or b.bite_cooldown < 0:
            errs.append("bad Bruno counters")
    return errs
