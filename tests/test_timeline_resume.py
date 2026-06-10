"""Tests for step-5: resume and rewind functionality."""

from agent.core.context import RunContext
from agent.core.runner import AgentRunner
from agent.llm.types import ModelResponse, Usage
from agent.middleware.chain import MiddlewareChain
from agent.steps.after_agent import BranchUpdateResumeHead, CheckpointRecordRunTerminalState, RunMarkTerminalState
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
from agent.steps.before_model import ModelRequestCompose
from agent.steps.registry import StepRegistry
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.models import CheckpointKind
from agent.timeline.resume import ResumeResult, resume
from agent.timeline.rewind import RewindResult, rewind
from agent.timeline.session_factory import create_session_with_default_branch


class MemorySQLiteTimelineStore(SQLiteTimelineStore):
    def search_memory(self, query: str) -> list[dict[str, str]]:
        return []


def _build_full_registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(ContextInitialize())
    reg.register(RunCreate())
    reg.register(MemoryPrefetch())
    reg.register(MessageCommitUser())
    reg.register(CheckpointCreateUserSnapshot())
    reg.register(BudgetInitialize())
    reg.register(ModelRequestCompose())
    reg.register(MessageCommitAssistant())
    reg.register(UsageUpdate())
    reg.register(ResultDetectFinalAnswer())
    reg.register(ToolDetectRequested())
    reg.register(MessageCommitToolResults())
    reg.register(CheckpointRecordToolResultsCommitted())
    reg.register(RunMarkTerminalState())
    reg.register(CheckpointRecordRunTerminalState())
    reg.register(BranchUpdateResumeHead())
    return reg


async def _run_agent(store: SQLiteTimelineStore, session_id: str, branch_id: str, user_input: str, model_fn=None):
    if model_fn is None:
        def model_fn(c: RunContext):
            return ModelResponse(content=f"reply to: {c.input}", usage=Usage(input_tokens=5, output_tokens=3))

    ctx = RunContext(input=user_input, session_id=session_id, branch_id=branch_id, timeline_store=store)
    reg = _build_full_registry()
    runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_fn)
    await runner.run_to_completion(ctx)
    return ctx


class TestSessionFactory:
    def test_create_session_with_default_branch(self):
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)

        assert session.active_branch_id != ""
        branch = store.get_branch(session.active_branch_id)
        assert branch is not None
        assert branch.session_id == session.session_id
        assert branch.parent_branch_id == ""


class TestBranchUpdateResumeHead:
    async def test_updates_on_completed_run(self):
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        ctx = await _run_agent(store, session.session_id, branch_id, "hello")
        assert ctx.status == "completed"

        branch = store.get_branch(branch_id)
        assert branch is not None
        assert branch.resume_head != ""

    async def test_does_not_update_on_failed_run(self):
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        def failing_model_call(c: RunContext):
            raise RuntimeError("boom")

        ctx = await _run_agent(store, session.session_id, branch_id, "hello", model_fn=failing_model_call)
        assert ctx.status == "failed"

        branch = store.get_branch(branch_id)
        assert branch is not None
        assert branch.resume_head == ""


class TestResumeMultiTurn:
    async def test_resume_restores_full_context(self):
        """After multiple turns, resume restores all messages."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "hello")
        await _run_agent(store, session.session_id, branch_id, "how are you?")
        await _run_agent(store, session.session_id, branch_id, "goodbye")

        result = resume(store, session.session_id)
        assert isinstance(result, ResumeResult)
        assert result.branch_id == branch_id

        roles = [m.role for m in result.messages]
        assert roles.count("user") == 3
        assert roles.count("assistant") == 3
        assert result.interrupted_info is None

    async def test_resume_model_sees_all_history(self):
        """Resume messages include content from all turns."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first question")
        await _run_agent(store, session.session_id, branch_id, "second question")

        result = resume(store, session.session_id)
        contents = [m.content for m in result.messages if m.role == "user"]
        assert "first question" in contents
        assert "second question" in contents

    async def test_second_turn_model_request_contains_prior_context(self):
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id
        requests: list[list[dict[str, object]]] = []

        def model_fn(c: RunContext):
            assert c.current_model_request is not None
            requests.append([dict(message) for message in c.current_model_request.messages])
            return ModelResponse(content=f"reply to: {c.input}", usage=Usage(input_tokens=5, output_tokens=3))

        await _run_agent(store, session.session_id, branch_id, "previous user", model_fn=model_fn)
        await _run_agent(store, session.session_id, branch_id, "current user", model_fn=model_fn)

        second_turn = requests[1]
        assert [m["role"] for m in second_turn] == ["system", "user", "assistant", "user"]
        assert [m["content"] for m in second_turn] == [
            "",
            "previous user",
            "reply to: previous user",
            "current user",
        ]


class TestRewind:
    async def test_rewind_creates_new_branch(self):
        """Rewind to a user message creates a new branch with correct context."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first")
        await _run_agent(store, session.session_id, branch_id, "second")
        await _run_agent(store, session.session_id, branch_id, "third")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        second_user_cp = user_snapshots[1]

        result = rewind(store, session.session_id, second_user_cp.checkpoint_id)
        assert isinstance(result, RewindResult)
        assert result.new_branch_id != branch_id

        user_msgs = [m for m in result.messages if m.role == "user"]
        assert len(user_msgs) == 2
        assert user_msgs[0].content == "first"
        assert user_msgs[1].content == "second"

        contents = [m.content for m in result.messages]
        assert "third" not in contents
        assert "partial..." not in contents

        assistant_msgs = [m for m in result.messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1

    async def test_old_branch_preserved(self):
        """After rewind, old branch history remains intact."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first")
        await _run_agent(store, session.session_id, branch_id, "second")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        first_user_cp = user_snapshots[0]

        rewind(store, session.session_id, first_user_cp.checkpoint_id)

        old_msgs = store.get_messages_by_branch(branch_id)
        roles = [m.role for m in old_msgs]
        assert roles.count("user") == 2
        assert roles.count("assistant") == 2

    async def test_new_branch_appends_normally(self):
        """After rewind, new branch accepts new messages normally."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first")
        await _run_agent(store, session.session_id, branch_id, "second")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        first_user_cp = user_snapshots[0]

        result = rewind(store, session.session_id, first_user_cp.checkpoint_id)
        new_branch_id = result.new_branch_id

        await _run_agent(store, session.session_id, new_branch_id, "new direction")

        new_msgs = store.get_messages_by_branch(new_branch_id)
        assert len(new_msgs) == 2
        assert new_msgs[0].role == "user"
        assert new_msgs[0].content == "new direction"
        assert new_msgs[1].role == "assistant"

    async def test_rewind_rejects_non_user_snapshot(self):
        """Rewind only works with user_snapshot checkpoints."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "hello")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        runtime_cp = [cp for cp in checkpoints if cp.kind == CheckpointKind.runtime][0]

        try:
            rewind(store, session.session_id, runtime_cp.checkpoint_id)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "user_snapshot" in str(e)


class TestInterruptedResume:
    async def test_resume_after_interrupted_run(self):
        """When last run was interrupted, resume goes to previous completed state."""
        store = MemorySQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first")
        await _run_agent(store, session.session_id, branch_id, "second")

        def interrupting_model_call(c: RunContext):
            c.interrupted = True
            return ModelResponse(content="partial...", usage=Usage(input_tokens=5, output_tokens=3))

        await _run_agent(store, session.session_id, branch_id, "third", model_fn=interrupting_model_call)

        result = resume(store, session.session_id)

        assert result.interrupted_info is not None
        assert "中断" in result.interrupted_info

        user_msgs = [m for m in result.messages if m.role == "user"]
        assert len(user_msgs) == 2
        assert user_msgs[0].content == "first"
        assert user_msgs[1].content == "second"

        contents = [m.content for m in result.messages]
        assert "third" not in contents
        assert "partial..." not in contents
