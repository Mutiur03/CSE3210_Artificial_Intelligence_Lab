"""Mamdani fuzzy logic: generic engine + Tom's and Jerry's mode controllers.

Engine (CLAUDE.md 4.4): triangular / trapezoid membership functions, AND = min,
implication = clip (min), aggregation = max, centroid defuzzification on the
output range 0..100 with step 1. The chosen mode is the output set with the
highest membership at the centroid (ties: the set listed first wins).

Rules are DATA: `(id, [(input variable, set), ...], output set)`, antecedents
ANDed. The tables below are copied from CLAUDE.md 4.4 and are what the viva
explains. No pygame here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Rule = tuple[str, list[tuple[str, str]], str]


@dataclass(frozen=True)
class MF:
    """Membership function. kind 'tri' (a, b, c) or 'trap' (a, b, c, d).

    A triangle is a trapezoid whose top is one point (b == c). Shoulders such
    as trap(0, 0, 3, 6) have a vertical left edge: membership 1 at x = 0.
    """

    kind: str
    params: tuple[float, ...]

    def __call__(self, x: float) -> float:
        a, b, c, d = self.params if self.kind == "trap" else (
            self.params[0], self.params[1], self.params[1], self.params[2])
        if x < a or x > d:
            return 0.0
        if b <= x <= c:
            return 1.0
        if x < b:
            return (x - a) / (b - a)
        return (d - x) / (d - c)


def tri(a: float, b: float, c: float) -> MF:
    """Triangle: 0 at a, rises to 1 at b, falls to 0 at c."""
    return MF("tri", (a, b, c))


def trap(a: float, b: float, c: float, d: float) -> MF:
    """Trapezoid: 0 at a, 1 from b to c, 0 at d."""
    return MF("trap", (a, b, c, d))


@dataclass(frozen=True)
class FuzzyVar:
    """A linguistic variable: crisp range [lo, hi] and named fuzzy sets (ordered)."""

    name: str
    lo: float
    hi: float
    sets: dict[str, MF]

    def fuzzify(self, x: float) -> dict[str, float]:
        """Membership of crisp `x` (clamped to the range) in every set."""
        x = min(self.hi, max(self.lo, x))
        return {name: mf(x) for name, mf in self.sets.items()}


@dataclass
class FuzzyResult:
    """Everything one evaluation produced. `trace` follows CLAUDE.md 4.8 when asked for."""

    mode: str
    output_memberships: dict[str, float]
    rule_strengths: dict[str, float]
    centroid: float
    memberships: dict[str, dict[str, float]]
    aggregated: list[tuple[int, float]] = field(repr=False)
    trace: dict | None = None


class FuzzySystem:
    """Generic Mamdani inference system.

    What: fuzzify the crisp inputs, fire every rule (strength = min of its
    antecedent memberships), clip each rule's output set at its strength,
    aggregate the clipped sets with max, take the centroid of the aggregated
    shape, and report the output set that is strongest at the centroid.
    Where used: TomController and JerryController pick each agent's mode every
    turn (NORMAL difficulty and above); the demo screen's fuzzy sliders.
    """

    def __init__(self, role: str, inputs: list[FuzzyVar], output: FuzzyVar, rules: list[Rule],
                 mode_names: dict[str, str] | None = None) -> None:
        self.role = role
        self.inputs = {v.name: v for v in inputs}
        self.output = output
        self.rules = rules
        self.mode_names = mode_names or {}

    @staticmethod
    def rule_text(rule: Rule) -> str:
        rid, ante, out = rule
        return " AND ".join(f"{v}={s}" for v, s in ante) + f" -> {out}"

    def evaluate(self, inputs: dict[str, float], trace: bool = False) -> FuzzyResult:
        """Run Mamdani inference on crisp `inputs` (one value per input variable)."""
        memberships = {name: var.fuzzify(inputs[name]) for name, var in self.inputs.items()}
        strengths = {rid: min(memberships[v][s] for v, s in ante) for rid, ante, _ in self.rules}
        # clip strength per output set: several rules may share one set -> max (aggregation)
        clip = dict.fromkeys(self.output.sets, 0.0)
        for rid, _, out in self.rules:
            clip[out] = max(clip[out], strengths[rid])
        lo, hi = int(self.output.lo), int(self.output.hi)
        aggregated = [(x, max(min(clip[s], mf(x)) for s, mf in self.output.sets.items()))
                      for x in range(lo, hi + 1)]
        area = sum(mu for _, mu in aggregated)
        # no rule fired: no shape to take a centroid of, report the middle of the range
        centroid = sum(x * mu for x, mu in aggregated) / area if area else (lo + hi) / 2
        out_mu = self.output.fuzzify(centroid)
        best = max(out_mu.values())
        out_set = next(s for s, mu in out_mu.items() if mu == best)
        mode = self.mode_names.get(out_set, out_set)
        res = FuzzyResult(mode, out_mu, strengths, centroid, memberships, aggregated)
        if trace:
            res.trace = {
                "type": "fuzzy", "role": self.role, "inputs": dict(inputs),
                "memberships": memberships,
                "rules": [{"id": rid, "text": self.rule_text((rid, ante, out)),
                           "strength": strengths[rid], "output": out}
                          for rid, ante, out in self.rules],
                "aggregated": [[x, mu] for x, mu in aggregated],
                "centroid": centroid, "output_memberships": out_mu, "mode": mode,
            }
        return res


# ------------------------------------------------------------------ Tom (4.4)

TOM_INPUTS = [
    FuzzyVar("dist", 0, 30, {"Near": trap(0, 0, 3, 6), "Mid": tri(4, 8, 13),
                             "Far": trap(10, 16, 30, 30)}),
    FuzzyVar("age", 0, 40, {"Fresh": trap(0, 0, 1, 4), "Stale": tri(2, 8, 16),
                            "Lost": trap(12, 20, 40, 40)}),
    FuzzyVar("bruno", 0, 1, {"Low": trap(0, 0, 0.2, 0.5), "High": trap(0.4, 0.7, 1, 1)}),
]
TOM_OUTPUT = FuzzyVar("pursuit", 0, 100, {
    "RETREAT": trap(0, 0, 8, 20), "SWEEP": tri(10, 30, 50), "AMBUSH": tri(40, 60, 80),
    "HUNT": trap(70, 85, 100, 100)})
TOM_RULES: list[Rule] = [
    ("T1", [("dist", "Near"), ("age", "Fresh"), ("bruno", "Low")], "HUNT"),
    ("T2", [("dist", "Mid"), ("age", "Fresh"), ("bruno", "Low")], "HUNT"),
    ("T3", [("dist", "Far"), ("age", "Fresh"), ("bruno", "Low")], "AMBUSH"),
    ("T4", [("dist", "Near"), ("age", "Stale"), ("bruno", "Low")], "HUNT"),
    ("T5", [("age", "Stale"), ("bruno", "Low")], "AMBUSH"),
    ("T6", [("age", "Lost"), ("bruno", "Low")], "SWEEP"),
    ("T7", [("bruno", "High")], "RETREAT"),
]

# ------------------------------------------------------------------ Jerry (4.4)

JERRY_INPUTS = [
    FuzzyVar("danger", 0, 30, {"Close": trap(0, 0, 3, 6), "Medium": tri(4, 8, 12),
                               "Safe": trap(9, 14, 30, 30)}),
    FuzzyVar("keys_left", 0, 3, {"Done": trap(0, 0, 0.4, 1), "Some": trap(0.6, 1, 3, 3)}),
    FuzzyVar("bruno_ready", 0, 1, {"No": trap(0, 0, 0.3, 0.6), "Yes": trap(0.4, 0.7, 1, 1)}),
]
JERRY_OUTPUT = FuzzyVar("urgency", 0, 100, {
    "SNEAK": trap(0, 0, 12, 30), "EVADE": tri(20, 40, 60), "BRUNO": tri(50, 65, 80),
    "DASH": trap(70, 85, 100, 100)})
JERRY_RULES: list[Rule] = [
    ("J1", [("danger", "Safe"), ("keys_left", "Some")], "SNEAK"),
    ("J2", [("danger", "Medium"), ("keys_left", "Some")], "EVADE"),
    ("J3", [("danger", "Close"), ("bruno_ready", "Yes")], "BRUNO"),
    ("J4", [("danger", "Close"), ("bruno_ready", "No")], "EVADE"),
    ("J5", [("keys_left", "Done"), ("danger", "Safe")], "DASH"),
    ("J6", [("keys_left", "Done"), ("danger", "Medium")], "DASH"),
    ("J7", [("keys_left", "Done"), ("danger", "Close")], "EVADE"),
]


class TomController(FuzzySystem):
    """Tom's mode selector: inputs dist, age, bruno -> HUNT / AMBUSH / SWEEP / RETREAT."""

    def __init__(self) -> None:
        super().__init__("TOM", TOM_INPUTS, TOM_OUTPUT, TOM_RULES)


class JerryController(FuzzySystem):
    """Jerry's mode selector: inputs danger, keys_left, bruno_ready -> SNEAK / EVADE /
    RUN_FOR_BRUNO / DASH (output set BRUNO is reported as mode RUN_FOR_BRUNO)."""

    def __init__(self) -> None:
        super().__init__("JERRY", JERRY_INPUTS, JERRY_OUTPUT, JERRY_RULES,
                         mode_names={"BRUNO": "RUN_FOR_BRUNO"})
