from pathlib import Path

import pygame
import pytest

import main
from game import JERRY, TOM, legal_actions


@pytest.fixture
def app() -> main.App:
    pygame.init()
    screen = pygame.display.set_mode((1100, 720))
    yield main.App(screen, main.parse_args(["--seed", "2", "--tom", "normal"]))
    pygame.quit()


def test_window_renders_screenshot(tmp_path: Path) -> None:
    out = tmp_path / "shot.png"
    main.main(["--seed", "3", "--auto", "5", "--screenshot", str(out)])
    assert out.stat().st_size > 1000


def test_menu_and_end_screens_draw(app: main.App) -> None:
    app.draw()
    assert len(app.rects) == len(main.App.ACTIONS) + len(app.options()) == 11
    app.start_game(main.PLAY_JERRY)
    s = app.session
    while s.state.winner is None:
        s.human_move("WAIT")
    app.scene = "end"
    app.draw()
    assert len(app.rects) == 3
    assert any("Tom" in line and "Jerry human" in line for line in s.stats())


def test_menu_options_cycle(app: main.App) -> None:
    app.selected = len(main.App.ACTIONS)  # Tom difficulty
    app.menu_activate(1)
    assert app.levels[TOM] == "HARD"
    app.selected += 2  # map size
    app.menu_activate(1)
    assert app.size == 27


def test_play_as_tom_and_overlays(app: main.App) -> None:
    app.start_game(main.PLAY_TOM)
    s = app.session
    assert s.human == TOM and JERRY in s.decisions  # Jerry already moved
    for key in (pygame.K_TAB, pygame.K_e, pygame.K_f):  # AI overlays: refused in human games
        app.game_key(key)
    assert not app.overlay["path"] and not app.overlay["explored"] and app.fuzzy_role is None
    for _ in range(10):
        if s.state.winner is None:
            s.human_move("WAIT")
    app.draw()


def test_human_game_hides_ai_plans_and_blocked_move_notice(app: main.App) -> None:
    """Human play never draws the AI's planned path or panel, and a wall bump says so."""
    app.start_game(main.PLAY_JERRY)
    app.overlay["path"] = True  # even if left on from a spectator game
    app.draw()
    assert app.session is not None and app.session.human == JERRY
    s = app.session
    blocked = next(a for a in ("UP", "DOWN", "LEFT", "RIGHT")
                   if a not in legal_actions(s.state, JERRY))
    app.game_key({"UP": pygame.K_UP, "DOWN": pygame.K_DOWN, "LEFT": pygame.K_LEFT,
                  "RIGHT": pygame.K_RIGHT}[blocked])
    assert app.notice.startswith("Blocked") and s.state.turn == 1  # no turn used
    app.draw()


def test_spectator_step_pause_speed(app: main.App) -> None:
    app.start_game(main.WATCH)
    s = app.session
    app.game_key(pygame.K_p)
    assert app.paused
    turn = s.state.turn
    app.game_key(pygame.K_n)
    assert s.state.turn == turn + 1 and TOM in s.decisions and JERRY in s.decisions
    app.game_key(pygame.K_PLUS)
    assert main.SPEEDS[app.speed] == 8
    app.game_key(pygame.K_f)
    app.game_key(pygame.K_f)
    assert app.fuzzy_role == JERRY
    app.draw()


def test_trace_toggle_saves_json(app: main.App, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "TRACE_DIR", tmp_path)
    app.start_game(main.WATCH)
    app.game_key(pygame.K_t)
    app.game_key(pygame.K_n)
    assert len(list(tmp_path.glob("2_1_*.json"))) == 2


def test_demo_every_algorithm_draws(app: main.App) -> None:
    app.open_demo()
    demo = app.demo
    for k in range(1, 9):
        demo.key(getattr(pygame, f"K_{k}"))
        for _ in range(30):
            demo.update()
        app.draw()
    demo.key(pygame.K_c)
    for _ in range(30):
        demo.update()
    app.draw()
    assert demo.res is not None and demo.res2 is not None


def test_help_overlay(app: main.App) -> None:
    app.run_action("How to Play")
    app.draw()
    assert app.help
