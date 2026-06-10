"""Tests for step-3: tool call pipeline."""

import json

from agent.actions.model_call import make_llm_call_action
from agent.actions.tool_call import make_tool_call_action
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
from agent.middleware.model import BudgetGuard, TraceRecord
from agent.middleware.tool import ApprovalGuard, AuditRecord, ResultLimitGuard
from agent.steps.after_model import (
    MessageCommitAssistant,
    ModelCaptureResponse,
    ResultDetectFinalAnswer,
    ToolDetectRequested,
    UsageUpdate,
)
from agent.steps.after_tool import MessageCommitToolResults, ToolResultsCapture
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
from agent.steps.before_tool import (
    ApprovalPrepareRequests,
    ToolCallsExtract,
    ToolCallsParseArguments,
    ToolCallsResolveTools,
    ToolCallsValidateSchema,
    ToolPlanBuildSerial,
)
from agent.steps.registry import StepRegistry
from agent.tools.base import ToolCall, ToolPlan, ToolResult, ToolResultStatus, ToolSpec
from agent.tools.builtin.think import think_tool
from agent.tools.dispatcher import ToolDispatcher
from agent.tools.registry import ToolRegistry


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


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(think_tool)
    return registry


def _build_full_registry(tool_registry: ToolRegistry | None = None) -> StepRegistry:
    reg = StepRegistry()
    tr = tool_registry or _build_tool_registry()

    # before_agent
    reg.register(ContextInitialize(
        guidance="You are a helpful assistant.\n\nBe concise.",
        model_config=ModelConfig(),
    ))
    reg.register(MemoryPrefetch())
    reg.register(MessageCommitUser())
    reg.register(ToolsSnapshotAvailableTools(registry=tr))
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

    # before_tool
    reg.register(ToolCallsExtract())
    reg.register(ToolCallsParseArguments())
    reg.register(ToolCallsValidateSchema())
    reg.register(ToolCallsResolveTools())
    reg.register(ToolPlanBuildSerial())
    reg.register(ApprovalPrepareRequests())

    # after_tool
    reg.register(ToolResultsCapture())
    reg.register(MessageCommitToolResults())

    return reg


def _build_middleware_chain() -> MiddlewareChain:
    chain = MiddlewareChain()
    chain.add(BudgetGuard())
    chain.add(TraceRecord())
    chain.add(ApprovalGuard())
    chain.add(AuditRecord())
    chain.add(ResultLimitGuard())
    return chain


class TestToolRegistry:
    """Test ToolRegistry register/get/list_schemas."""

    def test_register_and_get(self):
        registry = ToolRegistry()
        registry.register(think_tool)
        assert registry.get("think") is think_tool
        assert registry.get("nonexistent") is None

    def test_list_schemas(self):
        registry = ToolRegistry()
        registry.register(think_tool)
        schemas = registry.list_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "think"
        assert "thought" in schemas[0]["function"]["parameters"]["properties"]


class TestToolDispatcher:
    """Test ToolDispatcher serial execution."""

    def test_dispatch_success(self):
        registry = ToolRegistry()
        registry.register(think_tool)
        dispatcher = ToolDispatcher(registry)

        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="think", arguments={"thought": "hello"}),
        ])
        results = dispatcher.dispatch(plan)

        assert len(results) == 1
        assert results[0].status == ToolResultStatus.success
        assert results[0].content == "hello"
        assert results[0].call_id == "tc1"

    def test_dispatch_tool_not_found(self):
        registry = ToolRegistry()
        dispatcher = ToolDispatcher(registry)

        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="nonexistent", arguments={}),
        ])
        results = dispatcher.dispatch(plan)

        assert len(results) == 1
        assert results[0].status == ToolResultStatus.error
        assert "not found" in results[0].content.lower()

    def test_dispatch_with_error_marked_call(self):
        registry = ToolRegistry()
        registry.register(think_tool)
        dispatcher = ToolDispatcher(registry)

        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="think", arguments={}, error="parse failed"),
        ])
        results = dispatcher.dispatch(plan)

        assert len(results) == 1
        assert results[0].status == ToolResultStatus.error
        assert results[0].content == "parse failed"

    def test_dispatch_handler_exception(self):
        def bad_handler(**kwargs):
            raise ValueError("something went wrong")

        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="bad_tool",
            description="A tool that always fails",
            parameters_schema={"type": "object", "properties": {}},
            handler=bad_handler,
        ))
        dispatcher = ToolDispatcher(registry)

        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="bad_tool", arguments={}),
        ])
        results = dispatcher.dispatch(plan)

        assert len(results) == 1
        assert results[0].status == ToolResultStatus.error
        assert "ValueError" in results[0].content


class TestSingleRoundToolCall:
    """Task 3.23: Single tool call → final answer."""

    async def test_think_tool_then_answer(self):
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments=json.dumps({"thought": "Let me think about this..."}),
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="The answer is 42.",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=8),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="What is the meaning of life?")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "The answer is 42."
        assert ctx.iteration_index == 2
        assert call_count[0] == 2

        # Verify messages include tool results
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "tc1"
        assert "Let me think about this..." in tool_messages[0]["content"]


class TestMultiRoundToolCall:
    """Task 3.24: Multiple tool calls → final answer."""

    async def test_two_think_calls_then_answer(self):
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments=json.dumps({"thought": "First, consider X"}),
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc2",
                    name="think",
                    arguments=json.dumps({"thought": "Then, consider Y"}),
                )],
                usage=Usage(input_tokens=30, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Based on my analysis: the result is Z.",
                tool_calls=[],
                usage=Usage(input_tokens=40, output_tokens=12),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Analyze this problem")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "Based on my analysis: the result is Z."
        assert ctx.iteration_index == 3
        assert call_count[0] == 3

        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 2

    async def test_multiple_tool_calls_in_single_response(self):
        """Model requests multiple tools in one response (serial execution)."""
        responses = [
            ModelResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(id="tc1", name="think", arguments=json.dumps({"thought": "A"})),
                    ToolCallRequest(id="tc2", name="think", arguments=json.dumps({"thought": "B"})),
                ],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Done",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=5),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Do both things")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "Done"
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 2
        assert tool_messages[0]["content"] == "A"
        assert tool_messages[1]["content"] == "B"


class TestApprovalDenied:
    """Task 3.25: Approval denied → denied result → model continues."""

    async def test_denied_tool_generates_denied_result(self):
        """When approval.guard denies a call, model gets denied result and continues."""
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments=json.dumps({"thought": "thinking"}),
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="I'll proceed differently.",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=8),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)

        # Use a custom ApprovalGuard that denies all calls
        from agent.middleware.base import Middleware
        from agent.core.lifecycle import ActionName
        from typing import Any, Callable

        class DenyAllGuard(Middleware):
            def __init__(self):
                super().__init__("approval.guard", ActionName.tool_call)

            def __call__(self, ctx: RunContext, next_call: Callable[[], Any]) -> Any:
                plan: ToolPlan | None = ctx.current_tool_plan
                if plan is None:
                    return next_call()
                denied_results = []
                for call in plan.calls:
                    denied_results.append(ToolResult(
                        call_id=call.call_id,
                        status=ToolResultStatus.denied,
                        content="Permission denied: tool not approved",
                    ))
                plan.calls = []
                actual_results = next_call()
                if isinstance(actual_results, list):
                    return denied_results + actual_results
                return denied_results

        chain = MiddlewareChain()
        chain.add(BudgetGuard())
        chain.add(DenyAllGuard())
        chain.add(AuditRecord())

        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Do something")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "I'll proceed differently."
        # The denied result should be in messages
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "[DENIED]" in tool_messages[0]["content"]


class TestToolErrors:
    """Task 3.26: Tool not found / argument validation → error result."""

    async def test_unknown_tool_produces_error_result(self):
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="nonexistent_tool",
                    arguments=json.dumps({}),
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="I see that tool is not available.",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=8),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Use nonexistent tool")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "I see that tool is not available."
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "[ERROR]" in tool_messages[0]["content"]

    async def test_invalid_arguments_produces_error_result(self):
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments="not valid json {{{",
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Let me try again differently.",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=8),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Call with bad args")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        assert ctx.final_result == "Let me try again differently."
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "[ERROR]" in tool_messages[0]["content"]

    async def test_missing_required_param_produces_error_result(self):
        """Think tool requires 'thought' param — calling without it gives error."""
        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments=json.dumps({}),
                )],
                usage=Usage(input_tokens=20, output_tokens=10),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Missing param, adjusting.",
                tool_calls=[],
                usage=Usage(input_tokens=30, output_tokens=8),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Call without required param")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "[ERROR]" in tool_messages[0]["content"]
        assert "required" in tool_messages[0]["content"].lower()


class TestResultLimitGuard:
    """Test result_limit.guard truncation."""

    async def test_long_result_gets_truncated(self):
        def verbose_handler(**kwargs):
            return "x" * 100_000

        tool_registry = ToolRegistry()
        tool_registry.register(ToolSpec(
            name="verbose",
            description="Returns a very long string",
            parameters_schema={"type": "object", "properties": {}},
            handler=verbose_handler,
        ))

        responses = [
            ModelResponse(
                content="",
                tool_calls=[ToolCallRequest(id="tc1", name="verbose", arguments="{}")],
                usage=Usage(input_tokens=10, output_tokens=5),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Got truncated result.",
                tool_calls=[],
                usage=Usage(input_tokens=10, output_tokens=5),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class MultiClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(MultiClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="Run verbose tool")
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        tool_messages = [m for m in ctx.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "[Truncated" in tool_messages[0]["content"]
        assert len(tool_messages[0]["content"]) < 100_000


class TestSnapshotAvailableTools:
    """Test tools.snapshot_available_tools real logic."""

    async def test_snapshot_populates_available_tools(self):
        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()

        fake_response = ModelResponse(
            content="Hello",
            tool_calls=[],
            usage=Usage(input_tokens=5, output_tokens=5),
        )

        class SimpleClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                return fake_response

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(SimpleClient()),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert len(ctx.available_tools) == 1
        assert ctx.available_tools[0]["function"]["name"] == "think"

    async def test_model_request_includes_tools(self):
        """ModelRequest should include tool schemas from snapshot."""
        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()

        captured_request = [None]

        class CapturingClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                captured_request[0] = request
                return ModelResponse(
                    content="Done",
                    tool_calls=[],
                    usage=Usage(input_tokens=5, output_tokens=5),
                )

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(CapturingClient()),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        assert captured_request[0] is not None
        assert len(captured_request[0].tools) == 1
        assert captured_request[0].tools[0]["function"]["name"] == "think"


class TestReActLoopMessages:
    """Task 3.22: Verify messages accumulate correctly across ReAct rounds."""

    async def test_messages_visible_across_rounds(self):
        captured_messages = []
        responses = [
            ModelResponse(
                content="thinking...",
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="think",
                    arguments=json.dumps({"thought": "step 1"}),
                )],
                usage=Usage(input_tokens=10, output_tokens=5),
                finish_reason="tool_calls",
            ),
            ModelResponse(
                content="Final.",
                tool_calls=[],
                usage=Usage(input_tokens=20, output_tokens=5),
                finish_reason="stop",
            ),
        ]
        call_count = [0]

        class CapturingClient(LLMClient):
            def call(self, request: ModelRequest) -> ModelResponse:
                captured_messages.append([m.copy() for m in request.messages])
                idx = call_count[0]
                call_count[0] += 1
                return responses[idx]

        tool_registry = _build_tool_registry()
        step_registry = _build_full_registry(tool_registry)
        chain = _build_middleware_chain()
        dispatcher = ToolDispatcher(tool_registry)

        runner = AgentRunner(
            registry=step_registry,
            middleware_chain=chain,
            model_call=make_llm_call_action(CapturingClient()),
            tool_call=make_tool_call_action(dispatcher),
        )

        ctx = _ctx(input="test")
        await runner.run_to_completion(ctx)

        # Second call should see: user + assistant(tool_calls) + tool_result
        second_call_messages = captured_messages[1]
        roles = [m["role"] for m in second_call_messages]
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles

        # The assistant message should have tool_calls
        assistant_msgs = [m for m in second_call_messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert "tool_calls" in assistant_msgs[0]

        # The tool message should have the tool result
        tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "tc1"
        assert "step 1" in tool_msgs[0]["content"]
