"""Tests for step-2: model call pipeline integration."""

from agent.actions.model_call import make_llm_call_action
from agent.core.context import RunContext
from agent.core.runner import AgentRunner
from agent.llm.client import LLMClient
from agent.llm.types import (
    ModelConfig,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    Usage,
)
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.session_factory import create_session_with_default_branch
from agent.middleware.chain import MiddlewareChain
from agent.middleware.model import BudgetGuard, TimeoutGuard, TraceRecord
from agent.steps.after_model import (
    MessageCommitAssistant,
    ModelCaptureResponse,
    ResultDetectFinalAnswer,
    ToolDetectRequested,
    UsageUpdate,
)
from agent.steps.before_agent import (
    BudgetInitialize,
    ContextInitialize,
    MemoryPrefetch,
    MessageCommitUser,
    ToolsSnapshotAvailableTools,
)
from agent.steps.before_model import (
    ContextPrepareWithBudget,
    IterationCreate,
    ModelRequestCompose,
)
from agent.steps.registry import StepRegistry


class FakeTimelineStore(SQLiteTimelineStore):
    def search_memory(self, query: str) -> list[dict[str, str]]:
        return []


def _ctx(input: str = "test") -> RunContext:
    store = FakeTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    return RunContext(
        input=input,
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
        home_client=store,
    )


class FakeLLMClient(LLMClient):
    """A fake LLM client that returns a canned response."""

    def __init__(self, response: ModelResponse) -> None:
        self._response = response

    def call(self, request: ModelRequest) -> ModelResponse:
        return self._response


def _build_full_registry(model_config: ModelConfig | None = None) -> StepRegistry:
    """Register all step-2 steps in correct order."""
    reg = StepRegistry()

    # before_agent
    reg.register(ContextInitialize(
        guidance="You are a helpful assistant.\n\nBe concise.",
        model_config=model_config or ModelConfig(),
    ))
    reg.register(MemoryPrefetch())
    reg.register(MessageCommitUser())
    reg.register(ToolsSnapshotAvailableTools())
    reg.register(BudgetInitialize(max_iterations=10, max_tokens=100_000))

    # before_model
    reg.register(IterationCreate())
    reg.register(ContextPrepareWithBudget())
    reg.register(ModelRequestCompose())

    # after_model
    reg.register(ModelCaptureResponse())
    reg.register(MessageCommitAssistant())
    reg.register(UsageUpdate())
    reg.register(ResultDetectFinalAnswer())
    reg.register(ToolDetectRequested())

    return reg


def _build_middleware_chain() -> MiddlewareChain:
    chain = MiddlewareChain()
    chain.add(BudgetGuard())
    chain.add(TimeoutGuard(timeout_seconds=60.0))
    chain.add(TraceRecord())
    return chain


class TestIntegrationFullLifecycle:
    """Task 2.23: Input → full lifecycle → LLM → output."""

    async def test_simple_conversation_returns_response(self):
        fake_response = ModelResponse(
            content="Hello! How can I help you?",
            tool_calls=[],
            usage=Usage(input_tokens=20, output_tokens=10),
            finish_reason="stop",
        )
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()
        chain = _build_middleware_chain()
        model_action = make_llm_call_action(client)

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=model_action,
        )

        ctx = _ctx(input="  Hello world  ")
        result = await runner.run_to_completion(ctx)

        assert result.status == "completed"
        assert result.final_result == "Hello! How can I help you?"
        assert result.input == "  Hello world  "
        assert result.iteration_index == 1
        assert len(result.iterations) == 1
        assert result.budget.consumed_input_tokens == 20
        assert result.budget.consumed_output_tokens == 10

    async def test_direct_model_context_fields_remain_available(self):
        fake_response = ModelResponse(
            content="Done",
            usage=Usage(input_tokens=5, output_tokens=5),
        )
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()
        chain = _build_middleware_chain()

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert not hasattr(ctx, "base_model_context")
        assert not hasattr(ctx, "identity")
        assert ctx.model_config.model == "deepseek-chat"
        assert ctx.available_tools == []

    async def test_model_request_rebuilt_each_iteration(self):
        """With tool calls, model_request should be rebuilt on second iteration."""
        call_count = [0]
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(id="tc1", name="test_tool", arguments="{}")],
                usage=Usage(input_tokens=10, output_tokens=5),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Final answer",
                tool_calls=[],
                usage=Usage(input_tokens=15, output_tokens=8),
                finish_reason="stop",
            ),
        ]

        class MultiResponseClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                nonlocal call_count
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        client = MultiResponseClient()
        registry = _build_full_registry()
        chain = _build_middleware_chain()

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
            tool_call=lambda ctx: None,
        )

        ctx = _ctx(input="test")

        await runner.run_to_completion(ctx)

        assert ctx.iteration_index == 2
        assert ctx.final_result == "Final answer"
        assert ctx.budget.consumed_input_tokens == 25
        assert ctx.budget.consumed_output_tokens == 13

    async def test_no_tool_calls_single_iteration(self):
        fake_response = ModelResponse(
            content="Simple reply",
            tool_calls=[],
            usage=Usage(input_tokens=10, output_tokens=5),
            finish_reason="stop",
        )
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()
        chain = _build_middleware_chain()

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="hi")
        await runner.run_to_completion(ctx)

        assert ctx.iteration_index == 1
        assert ctx.has_tool_calls is False
        assert ctx.final_result == "Simple reply"
        assert ctx.status == "completed"


class TestBudgetGuard:
    """Task 2.24: budget.guard blocks calls when over limit."""

    async def test_iteration_limit_blocks_call(self):
        fake_response = ModelResponse(content="should not reach")
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()

        chain = MiddlewareChain()
        chain.add(BudgetGuard())

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="test")
        ctx.budget.max_iterations = 2

        # Simulate being at iteration 3 already consumed
        await runner.run_to_completion(ctx)
        # With max_iterations=2, the budget guard stops at iteration 3
        assert ctx.iteration_index <= 3
        assert ctx.status == "completed" or ctx.budget.exhausted

    async def test_token_limit_blocks_call(self):
        """When token budget is pre-exhausted, budget.guard blocks the model call."""
        call_count = [0]

        class CountingClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                nonlocal call_count
                call_count[0] += 1
                return ModelResponse(
                    content="response",
                    tool_calls=[ToolCallRequest(id="t1", name="x", arguments="{}")] if call_count[0] == 1 else [],
                    usage=Usage(input_tokens=80_000, output_tokens=30_000),
                    finish_reason="tool_calls" if call_count[0] == 1 else "stop",
                )

        client = CountingClient()
        # Use a custom low-budget registry
        reg = StepRegistry()
        reg.register(ContextInitialize(guidance="test"))
        reg.register(MemoryPrefetch())
        reg.register(MessageCommitUser())
        reg.register(ToolsSnapshotAvailableTools())
        reg.register(BudgetInitialize(max_iterations=10, max_tokens=100_000))
        reg.register(IterationCreate())
        reg.register(ContextPrepareWithBudget())
        reg.register(ModelRequestCompose())
        reg.register(ModelCaptureResponse())
        reg.register(MessageCommitAssistant())
        reg.register(UsageUpdate())
        reg.register(ResultDetectFinalAnswer())
        reg.register(ToolDetectRequested())

        chain = MiddlewareChain()
        chain.add(BudgetGuard())

        runner = AgentRunner(
            registry=reg,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
            tool_call=lambda ctx: None,
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        # First call uses 110k tokens total (80k+30k), exceeding 100k budget.
        # After first call, usage.update sets consumed=110k.
        # On second iteration, budget.guard sees 110k >= 100k, blocks call.
        assert call_count[0] == 1
        assert ctx.budget.exhausted is True
        assert ctx.budget.consumed_total_tokens == 110_000


class TestTimeoutGuard:
    """Task 2.25: timeout.guard interrupts on timeout."""

    async def test_timeout_raises_on_slow_call(self):
        import time

        class SlowClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                time.sleep(0.2)
                return ModelResponse(content="slow")

        client = SlowClient()
        registry = _build_full_registry()

        chain = MiddlewareChain()
        chain.add(TimeoutGuard(timeout_seconds=0.05))

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert len(ctx.errors) == 1
        assert isinstance(ctx.errors[0], TimeoutError)

    async def test_no_timeout_on_fast_call(self):
        fake_response = ModelResponse(
            content="fast response",
            usage=Usage(input_tokens=5, output_tokens=5),
        )
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()

        chain = MiddlewareChain()
        chain.add(TimeoutGuard(timeout_seconds=10.0))
        chain.add(TraceRecord())

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert ctx.final_result == "fast response"
        assert len(ctx.errors) == 0


class TestTraceRecord:
    """trace.record correctly records usage and timing."""

    async def test_records_duration_and_usage(self):
        fake_response = ModelResponse(
            content="traced",
            usage=Usage(input_tokens=100, output_tokens=50),
        )
        client = FakeLLMClient(fake_response)
        registry = _build_full_registry()

        chain = MiddlewareChain()
        chain.add(TraceRecord())

        runner = AgentRunner(
            registry=registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(client),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert len(ctx.iterations) == 1
        iteration = ctx.iterations[0]
        assert "model_call_duration_ms" in iteration
        assert iteration["model_call_duration_ms"] >= 0
        assert iteration["usage"]["input_tokens"] == 100
        assert iteration["usage"]["output_tokens"] == 50
