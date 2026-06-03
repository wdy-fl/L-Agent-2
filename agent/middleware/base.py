from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from agent.core.context import RunContext
from agent.core.lifecycle import ActionName


class Middleware(ABC):
    """Base class for action middleware (wraps model_call or tool_call)."""

    name: str
    target: ActionName

    def __init__(self, name: str, target: ActionName) -> None:
        self.name = name
        self.target = target

    @abstractmethod
    def __call__(self, ctx: RunContext, next_call: Callable[[], Any]) -> Any: ...
