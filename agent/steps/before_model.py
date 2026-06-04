from __future__ import annotations

from typing import Any, Callable

from agent.context.compressor import ContextCompressor, _estimate_tokens
from agent.core.context import RunContext
from agent.core.lifecycle import ActionName, HookPhase
from agent.llm.types import ModelRequest, ModelResponse
from agent.middleware.chain import MiddlewareChain
from agent.steps.base import Step


class IterationCreate(Step):
    """Increment iteration_index and record in ctx.iterations."""

    def __init__(self) -> None:
        super().__init__("iteration.create", HookPhase.before_model)

    def run(self, ctx: RunContext) -> None:
        ctx.iteration_index += 1
        ctx.iterations.append({
            "index": ctx.iteration_index,
            "status": "started",
        })
        ctx.budget.consumed_iterations += 1


class MessagesCollectVisible(Step):
    """Collect visible messages for this iteration's model call."""

    def __init__(self) -> None:
        super().__init__("messages.collect_visible", HookPhase.before_model)

    def run(self, ctx: RunContext) -> None:
        if not ctx.messages:
            ctx.messages = [{"role": "user", "content": ctx.input}]


class ContextPrepareWithBudget(Step):
    """Compress or truncate messages to fit context window.

    Uses LLM-based summarization (via middleware chain) when possible,
    falls back to FIFO truncation.
    """

    def __init__(
        self,
        compressor: ContextCompressor | None = None,
        max_context_tokens: int = 128_000,
        middleware_chain: MiddlewareChain | None = None,
        model_action: Callable[[RunContext], Any] | None = None,
    ) -> None:
        super().__init__("context.prepare_with_budget", HookPhase.before_model)
        self._compressor = compressor
        self._max_context_tokens = max_context_tokens
        self._chain = middleware_chain
        self._model_action = model_action

    def run(self, ctx: RunContext) -> None:
        estimated = sum(_estimate_tokens(m) for m in ctx.messages)

        if self._compressor and self._compressor.should_compress(estimated) and self._chain and self._model_action:
            call_llm = self._make_call_llm(ctx)
            ctx.messages = self._compressor.compress(ctx.messages, estimated, call_llm)
            estimated = sum(_estimate_tokens(m) for m in ctx.messages)

        while estimated > self._max_context_tokens and len(ctx.messages) > 1:
            ctx.messages.pop(0)
            estimated = sum(_estimate_tokens(m) for m in ctx.messages)

    def _make_call_llm(self, ctx: RunContext) -> Callable[[list[dict[str, Any]]], str]:
        def call_llm(messages: list[dict[str, Any]]) -> str:
            saved_request = ctx.current_model_request
            saved_response = ctx.current_model_response
            try:
                ctx.current_model_request = ModelRequest(messages=messages)
                result = self._chain.execute(  # type: ignore[union-attr]
                    ActionName.model_call, ctx, lambda: self._model_action(ctx)  # type: ignore[misc]
                )
                if isinstance(result, ModelResponse):
                    return result.content
                if ctx.current_model_response:
                    return ctx.current_model_response.content
                return ""
            finally:
                ctx.current_model_request = saved_request
                ctx.current_model_response = saved_response
        return call_llm


class ModelRequestCompose(Step):
    """Merge base_model_context + visible messages + params → ModelRequest."""

    def __init__(self) -> None:
        super().__init__("model_request.compose", HookPhase.before_model)

    def run(self, ctx: RunContext) -> None:
        base = ctx.base_model_context
        if base is None:
            ctx.current_model_request = ModelRequest(messages=ctx.messages)
            return

        system_parts: list[str] = []
        if base.guidance:
            system_parts.append(base.guidance)
        if base.workspace_context:
            system_parts.append(base.workspace_context)
        if base.memory_context:
            system_parts.append(base.memory_context)

        messages: list[dict[str, Any]] = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.extend(ctx.messages)

        ctx.current_model_request = ModelRequest(
            messages=messages,
            tools=base.available_tools,
            model=base.model_config.model,
            temperature=base.model_config.temperature,
            max_tokens=base.model_config.max_tokens,
        )
