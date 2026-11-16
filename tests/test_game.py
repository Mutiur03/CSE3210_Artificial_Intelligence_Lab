import pytest

import config as C
from agents import RandomAgent
from game import (
    CHASE_CAT,
    GUARD,
    JERRY,
    SLEEP,
    TIRED,
    TOM,
    apply_action,
    bruno_step,
    end_of_round,
    from_ascii,
    invariant_errors,
    legal_actions,
    make_observation,
    new_game,
    render_ascii,
    run_round,
)
from maze import generate_maze


def corridor(spec: str, **kw):
    """One-row map: spec index i is cell (1, i + 1)."""
    w = len(spec) + 2
    return from_ascii(f"{'#' * w}\n#{spec}#\n{'#' * w}", **kw)


def wait(_obs) -> str:
    return "WAIT"


OPEN = """
#######
#H....#
#..J..#
#.....#
#E...T#
#######
"""


# ------------------------------------------------------------------ actions


@pytest.mark.parametrize("action,expected", [
    ("UP", (1, 3)), ("DOWN", (3, 3)), ("LEFT", (2, 2)), ("RIGHT", (2, 4)), ("WAIT", (2, 3)),
])
def test_each_action(action: str, expected: tuple) -> None:
    s = from_ascii(OPEN)
    apply_action(s, JERRY, action)
    assert s.jerry == expected
    assert s.action_log == [(1, JERRY, action)]


def test_tom_moves_too() -> None:
    s = from_ascii(OPEN)
    apply_action(s, TOM, "UP")
    assert s.tom == (3, 5)


def test_wall_blocks() -> None:
    s = corridor("HJ.....TE")
    assert legal_actions(s, JERRY) == ["LEFT", "RIGHT", "WAIT"]
    with pytest.raises(ValueError):
        apply_action(s, JERRY, "UP")
    assert s.jerry == (1, 2)


def test_key_pickup() -> None:
    s = corridor("HJK.........TE")
    assert s.keys_taken == 2
    events = apply_action(s, JERRY, "RIGHT")
    assert s.keys_taken == 3 and s.keys == ()
    assert any("key" in e.text for e in events)


def test_exit_locked_does_nothing() -> None:
    s = corridor("HJE.....K....T")
    apply_action(s, JERRY, "RIGHT")
    assert s.jerry == s.maze.exit and not s.exit_open and s.winner is None


def test_exit_open_jerry_wins() -> None:
    s = corridor("HJE......T")
    assert s.exit_open
    apply_action(s, JERRY, "RIGHT")
    assert s.winner == JERRY


def test_alarm_reveals_exit_to_tom() -> None:
    s = corridor("HJK...........TE")
    assert make_observation(s, TOM).exit_cell is None
    assert make_observation(s, JERRY).exit_cell == s.maze.exit
    apply_action(s, JERRY, "RIGHT")
    obs = make_observation(s, TOM)
    assert s.exit_open and obs.exit_open and obs.exit_cell == s.maze.exit
    assert any("ALARM" in e for e in obs.events)


def test_capture_jerry_moves_into_tom() -> None:
    s = corridor("HJT....E")
    apply_action(s, JERRY, "RIGHT")
    assert s.winner == TOM and s.reason == "Jerry ran into Tom"


def test_capture_tom_moves_into_jerry() -> None:
    s = corridor("HJT....E")
    run_round(s, wait, lambda _o: "LEFT")
    assert s.winner == TOM and s.reason == "Tom caught Jerry"
    assert s.turn == 1  # game ended mid-round, no end_of_round


def test_turn_limit() -> None:
    s = corridor("HJ..........TE", turn=C.TURN_LIMIT - 1)
    run_round(s, wait, wait)
    assert s.winner is None and s.turn == C.TURN_LIMIT
    run_round(s, wait, wait)
    assert s.winner == TOM and "Time" in s.reason


def test_stun_skips_exactly_three_tom_actions() -> None:
    s = corridor("HJ.........T...E", stun=3)
    calls = []

    def tom(_obs) -> str:
        calls.append(1)
        return "LEFT"

    for _ in range(3):
        run_round(s, wait, tom)
        assert s.tom == (1, 12) and not calls
    assert s.tom_stun == 0
    assert legal_actions(s, TOM) != ["WAIT"]
    run_round(s, wait, tom)
    assert s.tom == (1, 11) and len(calls) == 1


def test_stunned_tom_may_only_wait() -> None:
    s = corridor("HJ.........T...E", stun=2)
    assert legal_actions(s, TOM) == ["WAIT"]
    with pytest.raises(ValueError):
        apply_action(s, TOM, "LEFT")


# ------------------------------------------------------------------ Bruno FSM


def test_bruno_wake() -> None:
    s = corridor("JH.......TE")
    assert s.bruno.state == SLEEP
    events = apply_action(s, JERRY, "RIGHT")
    b = s.bruno
    assert b.state == GUARD and b.guard_timer == C.BRUNO_GUARD_TURNS and b.activations == 1
    assert any("wakes" in e.text for e in events)


def test_bruno_activation_limit() -> None:
    s = corridor("JH.......TE", activations=2)
    apply_action(s, JERRY, "RIGHT")
    assert s.bruno.state == SLEEP and s.bruno.activations == 2


def test_bruno_guard_follows_jerry() -> None:
    s = corridor("HJ......B........TE")
    assert s.bruno.state == GUARD
    bruno_step(s)
    assert s.bruno.pos == (1, 8) and s.bruno.state == GUARD


def test_bruno_guard_stays_when_close() -> None:
    s = corridor("HJ.B.........TE")
    bruno_step(s)
    assert s.bruno.pos == (1, 4)


def test_bruno_chases_and_bites() -> None:
    s = corridor("HJ.B..T.......E")
    bruno_step(s)
    assert s.bruno.state == CHASE_CAT and s.bruno.pos == (1, 5) and s.tom_stun == 0
    bruno_step(s)
    b = s.bruno
    assert b.pos == (1, 6) and s.tom_stun == C.BRUNO_BITE_STUN
    assert b.bite_cooldown == C.BRUNO_BITE_COOLDOWN and b.state == GUARD and s.bites == 1


def test_bite_needs_cooldown_zero() -> None:
    s = corridor("HJ....BT......E", bruno_state=CHASE_CAT, bite_cooldown=2)
    bruno_step(s)
    assert s.tom_stun == 0 and s.bruno.state == CHASE_CAT


def test_cooldown_ticks_each_round() -> None:
    s = corridor("HJ.........T..E", bruno_state=TIRED, bite_cooldown=4, tired_timer=10)
    end_of_round(s)
    assert s.bruno.bite_cooldown == 3


def test_stunned_tom_not_chased() -> None:
    s = corridor("HJ.B..T.......E", stun=2)
    bruno_step(s)
    assert s.bruno.state == GUARD


def test_chase_gives_up_beyond_5() -> None:
    s = corridor("HJB.......T...E", bruno_state=CHASE_CAT)
    bruno_step(s)
    assert s.bruno.pos == (1, 4) and s.bruno.state == GUARD


def test_guard_timer_to_tired() -> None:
    s = corridor("HJ.B.........TE", guard_timer=2)
    end_of_round(s)
    assert s.bruno.state == GUARD and s.bruno.guard_timer == 1
    end_of_round(s)
    assert s.bruno.state == TIRED and s.bruno.tired_timer == C.BRUNO_TIRED_TURNS


def test_tired_walks_home_then_sleeps() -> None:
    s = corridor("H.B.J.........TE", bruno_state=TIRED, tired_timer=1)
    end_of_round(s)
    b = s.bruno
    assert b.pos == (1, 2) and b.tired_timer == 0 and b.state == TIRED  # not home yet
    end_of_round(s)
    assert b.pos == (1, 1) and b.state == SLEEP


def test_tired_waits_at_kennel_until_timer_ends() -> None:
    s = corridor("BJ..........TE", bruno_state=TIRED, tired_timer=2)
    end_of_round(s)
    assert s.bruno.state == TIRED
    end_of_round(s)
    assert s.bruno.state == SLEEP


def test_tired_bruno_cannot_be_woken() -> None:
    s = corridor("JB..........TE", bruno_state=TIRED, tired_timer=5)
    apply_action(s, JERRY, "RIGHT")
    assert s.bruno.state == TIRED


# ------------------------------------------------------------------ fog of war


def test_fog_hides_jerry_beyond_5() -> None:
    far = corridor("HJ.....T.E")  # distance 6
    assert make_observation(far, TOM).opp_pos is None
    assert make_observation(far, JERRY).opp_pos is None
    near = corridor("HJ....T..E")  # distance 5
    assert make_observation(near, TOM).opp_pos == near.jerry
    assert make_observation(near, TOM).opp_last_seen == (near.jerry, 1)


def test_fog_walls_block_vision() -> None:
    s = from_ascii("""
    #######
    #J#TH.#
    #.###.#
    #..E..#
    #######
    """)
    assert abs(s.jerry[1] - s.tom[1]) == 2  # close by Manhattan
    assert s.maze.dist(s.jerry, s.tom) > C.VISION_RADIUS
    assert make_observation(s, TOM).opp_pos is None


def test_fog_never_leaks_in_real_games() -> None:
    for seed in range(20):
        s = new_game(generate_maze(seed))
        a, b = RandomAgent(seed), RandomAgent(seed + 99)
        while s.winner is None:
            for role in (TOM, JERRY):
                obs = make_observation(s, role)
                d = s.maze.dist(s.jerry, s.tom)
                assert (obs.opp_pos is None) == (d > C.VISION_RADIUS)
                assert obs.bruno is None or obs.bruno[0] in obs.visible_cells
                assert all(s.maze.dist(obs.self_pos, c) <= 5 for c in obs.visible_cells)
            run_round(s, lambda o, a=a: a.act(o).action, lambda o, b=b: b.act(o).action)


def test_last_seen_ages() -> None:
    s = corridor("HJ....T........E")
    run_round(s, wait, lambda _o: "RIGHT")  # Tom walks out of sight
    run_round(s, wait, lambda _o: "RIGHT")
    obs = make_observation(s, TOM)
    assert obs.opp_pos is None and obs.opp_last_seen == ((1, 2), 1)


# ------------------------------------------------------------------ misc


def test_ascii_roundtrip() -> None:
    s = new_game(generate_maze(11))
    text = render_ascii(s)
    t = from_ascii(text)
    assert render_ascii(t) == text
    assert t.maze.floor == s.maze.floor and set(t.keys) == set(s.keys)
    assert t.bruno.pos == s.maze.kennel and t.bruno.state == SLEEP


def test_from_ascii_rejects_unknown_override() -> None:
    with pytest.raises(TypeError):
        corridor("HJ...T.E", speed=2)


def test_copy_is_independent() -> None:
    s = corridor("HJ.B..T.......E")
    c = s.copy()
    bruno_step(c)
    apply_action(c, JERRY, "LEFT")
    assert s.bruno.state == GUARD and s.jerry == (1, 2) and s.action_log == []
    assert c.copy(history=False).action_log == []


def test_same_seed_same_game() -> None:
    def play(seed: int):
        s = new_game(generate_maze(seed))
        a, b = RandomAgent(seed), RandomAgent(seed + 1)
        while s.winner is None:
            run_round(s, lambda o: a.act(o).action, lambda o: b.act(o).action)
        return s.action_log, s.winner, s.turn, render_ascii(s)

    assert play(8) == play(8)


def test_invariants_hold_initially() -> None:
    assert invariant_errors(new_game(generate_maze(1))) == []
