from scripts.random_game import play_games


def test_200_random_games_finish_cleanly() -> None:
    summary = play_games(200, size=21)
    assert summary["games"] == 200
    assert summary["jerry_wins"] + summary["tom_wins"] == 200
    assert summary["errors"] == []
