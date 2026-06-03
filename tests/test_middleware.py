"""Tests for middleware onion model execution."""

from typing import Any, Callable

from agent.core.context import RunContext
from agent.core.lifecycle import ActionName
from agent.middleware.base import Middleware
from agent.middleware.chain import MiddlewareChain


class LoggingMiddleware(Middleware):
    def __init__(self, name: str, target: ActionName, log: list[str]) -> None:
        super().__init__(name, target)
        self._log = log

    def __call__(self, ctx: RunContext, next_call: Callable[[], Any]) -> Any:
        self._log.append(f"enter:{self.name}")
        result = next_call()
        self._log.append(f"exit:{self.name}")
        return result


class TestMiddlewareChain:
    def test_onion_order(self):
        """Middleware should wrap in onion order: first added = outermost."""
        log: list[str] = []
        chain = MiddlewareChain()
        chain.add(LoggingMiddleware("outer", ActionName.model_call, log))
        chain.add(LoggingMiddleware("inner", ActionName.model_call, log))

        def action():
            log.append("action")
            return "result"

        ctx = RunContext()
        result = chain.execute(ActionName.model_call, ctx, action)

        assert result == "result"
        assert log == [
            "enter:outer",
            "enter:inner",
            "action",
            "exit:inner",
            "exit:outer",
        ]

    def test_middleware_filters_by_target(self):
        """Only middleware matching the target action should execute."""
        log: list[str] = []
        chain = MiddlewareChain()
        chain.add(LoggingMiddleware("model_mw", ActionName.model_call, log))
        chain.add(LoggingMiddleware("tool_mw", ActionName.tool_call, log))

        def action():
            log.append("action")
            return "ok"

        ctx = RunContext()
        chain.execute(ActionName.model_call, ctx, action)

        assert log == ["enter:model_mw", "action", "exit:model_mw"]

    def test_empty_chain_executes_action_directly(self):
        """With no middleware, action should execute directly."""
        chain = MiddlewareChain()
        called = [False]

        def action():
            called[0] = True
            return 42

        ctx = RunContext()
        result = chain.execute(ActionName.model_call, ctx, action)

        assert called[0]
        assert result == 42

    def test_middleware_can_modify_result(self):
        """Middleware can transform the action result."""

        class DoublingMiddleware(Middleware):
            def __call__(self, ctx: RunContext, next_call: Callable[[], Any]) -> Any:
                result = next_call()
                return result * 2

        chain = MiddlewareChain()
        chain.add(DoublingMiddleware("doubler", ActionName.model_call))

        ctx = RunContext()
        result = chain.execute(ActionName.model_call, ctx, lambda: 5)

        assert result == 10
