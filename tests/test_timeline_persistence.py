"""Tests for step-4: timeline persistence and checkpoint correctness."""

import uuid

from agent.core.context import RunContext
from agent.core.runner import AgentRunner
from agent.llm.types import ModelResponse, ToolCallRequest, Usage
from agent.middleware.chain import MiddlewareChain
from agent.steps.after_agent import CheckpointRecordRunTerminalState, RunMarkTerminalState
from agent.steps.after_model import MessageCommitAssistant, ResultDetectFinalAnswer, ToolDetectRequested, UsageUpdate
from agent.steps.after_tool import CheckpointRecordToolResultsCommitted, MessageCommitToolResults
from agent.steps.before_agent import (
    BudgetInitialize,
    CheckpointCreateUserSnapshot,
    ContextInitialize,
    MemoryPrefetch,
    MessageCommitUser,
    RunCreate,
)
from agent.steps.registry import StepRegistry
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.models import Branch, CheckpointKind, RunStatus, Session
from agent.tools.base import ToolResult


class EmptyMemoryClient:
    def search_memory(self, query: str) -> list[dict[str, str]]:
        return []


def _make_store_and_ctx(user_input: str = "hello") -> tuple[SQLiteTimelineStore, RunContext]:
    store = SQLiteTimelineStore(":memory:")
    session_id = str(uuid.uuid4())
    branch_id = str(uuid.uuid4())
    store.create_session(Session(session_id=session_id, active_branch_id=branch_id))
    store.create_branch(Branch(branch_id=branch_id, session_id=session_id))
    ctx = RunContext(
        input=user_input,
        session_id=session_id,
        branch_id=branch_id,
        timeline_store=store,
        home_client=EmptyMemoryClient(),
    )
    return store, ctx


def _build_full_registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(ContextInitialize())
    reg.register(BudgetInitialize())
    reg.register(RunCreate())
    reg.register(MemoryPrefetch())
    reg.register(MessageCommitUser())
    reg.register(CheckpointCreateUserSnapshot())
    reg.register(MessageCommitAssistant())
    reg.register(UsageUpdate())
    reg.register(ResultDetectFinalAnswer())
    reg.register(ToolDetectRequested())
    reg.register(MessageCommitToolResults())
    reg.register(CheckpointRecordToolResultsCommitted())
    reg.register(RunMarkTerminalState())
    reg.register(CheckpointRecordRunTerminalState())
    return reg


class TestFullAgentRunPersistence:
    async def test_complete_run_persists_all_records(self):
        """A full run with one tool call creates session/branch/run/messages/checkpoints."""
        store, ctx = _make_store_and_ctx("what time is it?")
        reg = _build_full_registry()
        call_count = [0]

        def model_call(c: RunContext):
            call_count[0] += 1
            if call_count[0] == 1:
                return ModelResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id="tc1", name="clock", arguments="{}")],
                    usage=Usage(input_tokens=10, output_tokens=5),
                )
            return ModelResponse(content="It is 3pm.", usage=Usage(input_tokens=8, output_tokens=4))

        def tool_call(c: RunContext):
            return [ToolResult(call_id="tc1", content="15:00")]

        runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_call, tool_call=tool_call)
        await runner.run_to_completion(ctx)

        assert ctx.status == "completed"
        run = store.get_run(ctx.run_id)
        assert run is not None
        assert run.status == RunStatus.completed

        msgs = store.get_messages_by_branch(ctx.branch_id)
        roles = [m.role for m in msgs]
        assert roles == ["system", "user", "assistant", "tool", "assistant"]

        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        assert len(checkpoints) > 0
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        assert len(user_snapshots) == 1
        assert user_snapshots[0].name == "user_message_committed"


class TestMessageSequence:
    async def test_sequence_increments_correctly(self):
        """Messages have strictly incrementing sequence numbers with no gaps."""
        store, ctx = _make_store_and_ctx("hi")
        reg = _build_full_registry()

        def model_call(c: RunContext):
            return ModelResponse(content="hello!", usage=Usage(input_tokens=5, output_tokens=3))

        runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_call)
        await runner.run_to_completion(ctx)

        msgs = store.get_messages_by_branch(ctx.branch_id)
        sequences = [m.sequence for m in msgs]
        assert sequences == list(range(len(sequences)))


class TestCheckpointCursor:
    async def test_user_snapshot_cursor_points_to_user_message(self):
        """user_message_committed checkpoint cursor equals user message sequence."""
        store, ctx = _make_store_and_ctx("test input")
        reg = _build_full_registry()

        def model_call(c: RunContext):
            return ModelResponse(content="ok", usage=Usage(input_tokens=5, output_tokens=2))

        runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_call)
        await runner.run_to_completion(ctx)

        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        user_cp = [cp for cp in checkpoints if cp.name == "user_message_committed"][0]
        msgs = store.get_messages_by_branch(ctx.branch_id)
        user_msg = [m for m in msgs if m.role == "user"][0]
        assert user_cp.message_cursor == user_msg.sequence


class TestRuntimeCheckpoints:
    async def test_runtime_checkpoints_recorded_for_actions(self):
        """model_call_started/completed and tool_call_started/completed are recorded."""
        store, ctx = _make_store_and_ctx("do something")
        reg = _build_full_registry()
        call_count = [0]

        def model_call(c: RunContext):
            call_count[0] += 1
            if call_count[0] == 1:
                return ModelResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id="tc1", name="do", arguments="{}")],
                    usage=Usage(input_tokens=5, output_tokens=3),
                )
            return ModelResponse(content="done", usage=Usage(input_tokens=5, output_tokens=2))

        def tool_call(c: RunContext):
            return [ToolResult(call_id="tc1", content="result")]

        runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_call, tool_call=tool_call)
        await runner.run_to_completion(ctx)

        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        names = [cp.name for cp in checkpoints]
        assert "model_call_started" in names
        assert "model_call_completed" in names
        assert "tool_call_started" in names
        assert "tool_call_completed" in names
        assert "tool_results_committed" in names
        assert "run_completed" in names
