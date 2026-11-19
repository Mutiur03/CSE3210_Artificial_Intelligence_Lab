import itertools

import pytest

from fuzzy import (
    JERRY_INPUTS,
    JERRY_OUTPUT,
    TOM_INPUTS,
    TOM_OUTPUT,
    TOM_RULES,
    JerryController,
    TomController,
)


def test_memberships_stay_in_unit_interval() -> None:
    for var in TOM_INPUTS + JERRY_INPUTS + [TOM_OUTPUT, JERRY_OUTPUT]:
        steps = 200
        for i in range(-10, steps + 11):  # also outside the range (clamped)
            x = var.lo + (var.hi - var.lo) * i / steps
            for mu in var.fuzzify(x).values():
                assert 0.0 <= mu <= 1.0


def test_engine_outputs_stay_in_unit_interval() -> None:
    tom = TomController()
    for d, a, b in itertools.product(range(0, 31, 3), range(0, 41, 4), (0, 0.3, 0.5, 0.8, 1)):
        r = tom.evaluate({"dist": d, "age": a, "bruno": b})
        assert all(0 <= v <= 1 for v in r.rule_strengths.values())
        assert all(0 <= v <= 1 for v in r.output_memberships.values())
        assert all(0 <= mu <= 1 for _, mu in r.aggregated)
        assert 0 <= r.centroid <= 100


@pytest.mark.parametrize("inputs, mode", [
    ({"dist": 2, "age": 0, "bruno": 0}, "HUNT"),       # T1: Jerry right there
    ({"dist": 8, "age": 0, "bruno": 0}, "HUNT"),       # T2: Jerry seen, mid range
    ({"dist": 25, "age": 0, "bruno": 0}, "AMBUSH"),    # T3: seen but far: cut her off
    ({"dist": 12, "age": 8, "bruno": 0}, "AMBUSH"),    # T5: stale sighting
    ({"dist": 30, "age": 40, "bruno": 0}, "SWEEP"),    # T6: lost
    ({"dist": 3, "age": 0, "bruno": 0.9}, "RETREAT"),  # T7: Bruno about to bite
])
def test_tom_controller_cases(inputs: dict, mode: str) -> None:
    assert TomController().evaluate(inputs).mode == mode


@pytest.mark.parametrize("inputs, mode", [
    ({"danger": 20, "keys_left": 2, "bruno_ready": 0}, "SNEAK"),         # J1
    ({"danger": 8, "keys_left": 2, "bruno_ready": 1}, "EVADE"),          # J2
    ({"danger": 2, "keys_left": 2, "bruno_ready": 1}, "RUN_FOR_BRUNO"),  # J3
    ({"danger": 2, "keys_left": 1, "bruno_ready": 0}, "EVADE"),          # J4
    ({"danger": 25, "keys_left": 0, "bruno_ready": 1}, "DASH"),          # J5
])
def test_jerry_controller_cases(inputs: dict, mode: str) -> None:
    assert JerryController().evaluate(inputs).mode == mode


def _tri(a: float, b: float, c: float, x: float) -> float:
    return max(0.0, min((x - a) / (b - a), (c - x) / (c - b)))


def _trap(a: float, b: float, c: float, d: float, x: float) -> float:
    left = 1.0 if a == b else (x - a) / (b - a)
    right = 1.0 if c == d else (d - x) / (d - c)
    return max(0.0, min(left, 1.0, right))


def test_centroid_matches_hand_formula() -> None:
    """dist=5, age=3, bruno=0, worked out by hand:
    Near(5)=1/3, Mid(5)=1/4, Fresh(3)=1/3, Stale(3)=1/6, Low(0)=1.
    T1=min(1/3,1/3,1)=1/3, T2=1/4, T4=min(1/3,1/6)=1/6 -> HUNT clip 1/3;
    T5=1/6 -> AMBUSH clip 1/6. Centroid = sum(x*mu) / sum(mu), x = 0..100."""
    res = TomController().evaluate({"dist": 5, "age": 3, "bruno": 0}, trace=True)
    assert res.rule_strengths["T1"] == pytest.approx(1 / 3)
    assert res.rule_strengths["T2"] == pytest.approx(1 / 4)
    assert res.rule_strengths["T4"] == pytest.approx(1 / 6)
    assert res.rule_strengths["T5"] == pytest.approx(1 / 6)
    num = den = 0.0
    for x in range(101):
        mu = max(min(1 / 3, _trap(70, 85, 100, 100, x)), min(1 / 6, _tri(40, 60, 80, x)))
        num += x * mu
        den += mu
    assert res.centroid == pytest.approx(num / den)
    tr = res.trace
    assert tr is not None and tr["type"] == "fuzzy" and tr["mode"] == res.mode
    agg = tr["aggregated"]
    assert len(agg) == 101
    assert tr["centroid"] == pytest.approx(sum(x * mu for x, mu in agg) / sum(mu for _, mu in agg))
    assert {r["id"] for r in tr["rules"]} == {f"T{i}" for i in range(1, 8)}


def test_rules_are_data() -> None:
    assert TOM_RULES[0] == ("T1", [("dist", "Near"), ("age", "Fresh"), ("bruno", "Low")], "HUNT")
    assert TomController.rule_text(TOM_RULES[6]) == "bruno=High -> RETREAT"
