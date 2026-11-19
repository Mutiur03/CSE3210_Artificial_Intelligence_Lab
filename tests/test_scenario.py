"""The scenario files must match the live agents and be reproducible."""

import re
from pathlib import Path

import pytest

import scenario_report
from agents import make_agent
from game import JERRY, TOM, from_ascii, make_observation
from scenario import MAP, SEED, TURN, build_bruno_scenario
from scenario_report import build_all


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("scenario")
    build_all(path)
    return path


def grab(text: str, label: str) -> str:
    return re.search(rf"\*\*{label}:\*\*\s*(\S+)", text).group(1)


def test_position_is_as_specified() -> None:
    s = from_ascii(MAP, turn=TURN)
    assert s.maze.dist(s.jerry, s.tom) == 3 and s.keys_taken == 2 and len(s.keys) == 1
    assert s.bruno.state == "SLEEP" and s.bruno.activations == 0
    assert make_observation(s, TOM).opp_pos == s.jerry
    assert make_observation(s, JERRY).opp_pos == s.tom


def test_markdown_equals_live_agents(out: Path) -> None:
    s = from_ascii(MAP, turn=TURN)
    for role, key in ((TOM, "tom"), (JERRY, "jerry")):
        d = make_agent(role, "HARD", SEED).act(make_observation(s, role))
        fz = (out / f"fuzzy_{key}.md").read_text(encoding="utf-8")
        assert grab(fz, "Mode") == d.mode
        assert float(grab(fz, "Centroid")) == pytest.approx(
            _centroid(role, d.fuzzy_inputs), abs=0.005)
        mm = (out / "minimax.md").read_text(encoding="utf-8")
        block = mm.split("## Tom to move" if role == TOM else "## Jerry to move")[1]
        block = block.split("## Jerry to move")[0] if role == TOM else block
        assert grab(block, "Chosen") == d.action
        assert int(grab(block, "Nodes")) == d.nodes
        walk = (out / "walkthrough.md").read_text(encoding="utf-8")
        assert f"## {role.title()} (HARD): {d.action}" in walk


def _centroid(role: str, inputs: dict) -> float:
    from fuzzy import JerryController, TomController
    ctl = TomController() if role == TOM else JerryController()
    return ctl.evaluate(inputs).centroid


def test_minimax_value_equals_live(out: Path) -> None:
    import minimax
    from game import belief_state
    s = from_ascii(MAP, turn=TURN)
    obs = make_observation(s, TOM)
    res = minimax.decide(belief_state(obs, obs.opp_pos), TOM)
    mm = (out / "minimax.md").read_text(encoding="utf-8")
    assert f"| root value (Tom's view) | **{res.value:g}**".replace("-", "-") in mm


def test_build_twice_identical(out: Path, tmp_path: Path) -> None:
    build_all(tmp_path)
    names = sorted(p.relative_to(out) for p in out.rglob("*") if p.is_file())
    assert len(names) == 16
    for n in names:
        assert (out / n).read_bytes() == (tmp_path / n).read_bytes(), n


def test_bruno_scenario_bites_and_stuns() -> None:
    state, frames = build_bruno_scenario()
    assert state.bites == 1 and frames[-1].tom_stun == 0
    assert max(f.tom_stun for f in frames) == 3
    assert any("wakes up" in e for f in frames for e in f.events)
    assert scenario_report.cell((1, 2)) == "(1,2)"
