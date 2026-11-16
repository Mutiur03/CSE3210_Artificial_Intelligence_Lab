"""AI agents. Every agent turns an Observation into a Decision (CLAUDE.md 4.1).

Phase 1 has only RandomAgent; search-based agents arrive in later phases.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from game import Observation, moves_from


@dataclass
class Decision:
    """One AI move plus everything the UI shows about how it was chosen."""

    action: str
    mode: str
    algorithm: str
    nodes: int
    ms: float
    fuzzy_inputs: dict | None = None
    rule_strengths: dict | None = None
    path: list[tuple] = field(default_factory=list)
    explored: list[tuple] = field(default_factory=list)
    trace: dict | None = None


class Agent(ABC):
    """Base class. Agents only ever receive Observations, never GameState."""

    name = "Agent"

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    @abstractmethod
    def act(self, obs: Observation) -> Decision:
        """Choose this turn's action."""


class RandomAgent(Agent):
    """Picks a uniformly random legal action (seeded). Baseline and Phase 1 Tom."""

    name = "Random"

    def act(self, obs: Observation) -> Decision:
        t0 = time.perf_counter()
        options = moves_from(obs.maze, obs.self_pos)
        action = self.rng.choice(options)
        return Decision(
            action=action, mode="SCRIPTED", algorithm="Random legal move",
            nodes=len(options), ms=(time.perf_counter() - t0) * 1000,
        )
