from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.core.lifecycle import HookPhase
from agent.steps.base import Step


@dataclass
class StepConfig:
    enabled: bool = True
    priority: int = 100
    params: dict[str, Any] = field(default_factory=dict)


class StepRegistry:
    """Manages step registration, configuration, and phase-based lookup."""

    def __init__(self) -> None:
        self._steps: list[Step] = []
        self._configs: dict[str, StepConfig] = {}

    def register(self, step: Step, config: StepConfig | None = None) -> None:
        self._steps.append(step)
        if config is not None:
            self._configs[step.name] = config

    def configure(self, name: str, **kwargs: Any) -> None:
        cfg = self._configs.setdefault(name, StepConfig())
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    def get_steps(self, phase: HookPhase) -> list[Step]:
        result: list[Step] = []
        for step in self._steps:
            if step.phase != phase:
                continue
            cfg = self._configs.get(step.name, StepConfig())
            if not cfg.enabled:
                continue
            result.append(step)
        result.sort(key=lambda s: self._configs.get(s.name, StepConfig()).priority)
        return result
