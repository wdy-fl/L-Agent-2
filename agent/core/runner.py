from __future__ import annotations

from typing import Any, Callable

from agent.core.context import RunContext
from agent.core.lifecycle import ActionName, HookPhase
from agent.middleware.chain import MiddlewareChain
from agent.steps.registry import StepRegistry


class AgentRunner:
    """Drives a single AgentRun through the fixed eight-phase lifecycle."""

    def __init__(
        self,
        registry: StepRegistry,
        middleware_chain: MiddlewareChain,
        model_call: Callable[[RunContext], Any] | None = None,
        tool_call: Callable[[RunContext], Any] | None = None,
    ) -> None:
        self._registry = registry
        self._chain = middleware_chain
        self._model_call = model_call or self._noop_model_call
        self._tool_call = tool_call or self._noop_tool_call

    def run(self, ctx: RunContext) -> RunContext:
        try:
            self._run_phase(HookPhase.before_agent, ctx)
            self._react_loop(ctx)
        except Exception as exc:
            ctx.errors.append(exc)
        finally:
            self._run_phase(HookPhase.after_agent, ctx)
        return ctx

    def _react_loop(self, ctx: RunContext) -> None:
        while True:
            if ctx.interrupted:
                break

            ctx.iterations += 1
            self._run_phase(HookPhase.before_model, ctx)

            self._execute_action(ActionName.model_call, ctx, self._model_call)

            self._run_phase(HookPhase.after_model, ctx)

            if ctx.has_tool_calls:
                self._run_phase(HookPhase.before_tool, ctx)
                self._execute_action(ActionName.tool_call, ctx, self._tool_call)
                self._run_phase(HookPhase.after_tool, ctx)
                ctx.has_tool_calls = False
            else:
                break

    def _run_phase(self, phase: HookPhase, ctx: RunContext) -> None:
        for step in self._registry.get_steps(phase):
            step.run(ctx)

    def _execute_action(
        self, action_name: ActionName, ctx: RunContext, action: Callable[[RunContext], Any]
    ) -> None:
        self._record_checkpoint(action_name, "started", ctx)
        try:
            result = self._chain.execute(action_name, ctx, lambda: action(ctx))
            if action_name == ActionName.model_call:
                ctx.current_model_response = result
            elif action_name == ActionName.tool_call:
                ctx.current_tool_results = result
            self._record_checkpoint(action_name, "completed", ctx)
        except Exception as exc:
            self._record_checkpoint(action_name, "failed", ctx)
            raise exc

    def _record_checkpoint(self, action: ActionName, status: str, ctx: RunContext) -> None:
        pass

    @staticmethod
    def _noop_model_call(ctx: RunContext) -> Any:
        ctx.final_result = ""
        return None

    @staticmethod
    def _noop_tool_call(ctx: RunContext) -> Any:
        return None
