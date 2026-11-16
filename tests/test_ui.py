from pathlib import Path

import main


def test_window_renders_screenshot(tmp_path: Path) -> None:
    out = tmp_path / "shot.png"
    main.main(["--seed", "3", "--auto", "5", "--screenshot", str(out)])
    assert out.stat().st_size > 1000


def test_menu_and_end_screens_draw() -> None:
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((1100, 720))
    app = main.App(screen, main.parse_args(["--seed", "2"]))
    app.draw()
    assert len(app.rects) == 5
    app.start_game()
    s = app.session
    while s.state.winner is None:
        s.human_move("WAIT")
    app.scene = "end"
    app.draw()
    assert len(app.rects) == 3
    pygame.quit()
