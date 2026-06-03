from __future__ import annotations

from typing import Any, Callable

from agent.core.context import RunContext
from agent.core.lifecycle import ActionName
from agent.middleware.base import Middleware


class MiddlewareChain:
    """Assembles middleware in onion model around an action."""

    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def add(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def execute(
        self, target: ActionName, ctx: RunContext, action: Callable[[], Any]
    ) -> Any:
        chain = [m for m in self._middlewares if m.target == target]

        def build(index: int) -> Callable[[], Any]:
            if index >= len(chain):
                return action
            mw = chain[index]
            return lambda: mw(ctx, build(index + 1))

        return build(0)()
