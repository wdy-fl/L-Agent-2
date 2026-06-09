"""Tests for step-5: rewind branch correctness."""

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
    MessageCommitUser,
    RunCreate,
)
from agent.steps.registry import StepRegistry
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.models import CheckpointKind
from agent.timeline.resume import collect_branch_messages, resume
from agent.timeline.rewind import rewind
from agent.timeline.session_factory import create_session_with_default_branch


def _build_full_registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(ContextInitialize())
    reg.register(BudgetInitialize())
    reg.register(RunCreate())
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
    reg.register(BranchUpdateResumeHead())
    return reg


async def _run_agent(store: SQLiteTimelineStore, session_id: str, branch_id: str, user_input: str):
    def model_fn(c: RunContext):
        return ModelResponse(content=f"reply to: {c.input}", usage=Usage(input_tokens=5, output_tokens=3))

    ctx = RunContext(input=user_input, session_id=session_id, branch_id=branch_id, timeline_store=store)
    reg = _build_full_registry()
    runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_fn)
    await runner.run_to_completion(ctx)
    return ctx


class TestRewindContextCorrectness:
    async def test_rewind_includes_user_message_excludes_assistant(self):
        """Rewind context includes the user message at fork point but not its assistant reply."""
        store = SQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "first")
        await _run_agent(store, session.session_id, branch_id, "second")
        await _run_agent(store, session.session_id, branch_id, "third")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        second_cp = user_snapshots[1]

        result = rewind(store, session.session_id, second_cp.checkpoint_id)

        user_contents = [m.content for m in result.messages if m.role == "user"]
        assert "first" in user_contents
        assert "second" in user_contents
        assert "third" not in user_contents

        assistant_contents = [m.content for m in result.messages if m.role == "assistant"]
        assert len(assistant_contents) == 1
        assert "first" in assistant_contents[0]

    async def test_rewind_does_not_modify_checkpoint_before_history(self):
        """Messages before the fork point are never modified."""
        store = SQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "AAA")
        await _run_agent(store, session.session_id, branch_id, "BBB")

        msgs_before = store.get_messages_by_branch(branch_id)
        contents_before = [(m.role, m.content) for m in msgs_before]

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]
        rewind(store, session.session_id, user_snapshots[0].checkpoint_id)

        msgs_after = store.get_messages_by_branch(branch_id)
        contents_after = [(m.role, m.content) for m in msgs_after]
        assert contents_before == contents_after


class TestBranchStructureSharing:
    async def test_new_branch_does_not_copy_messages(self):
        """New branch has no messages of its own initially — uses parent via cursor."""
        store = SQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "hello")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]

        result = rewind(store, session.session_id, user_snapshots[0].checkpoint_id)

        own_msgs = store.get_messages_by_branch(result.new_branch_id)
        assert len(own_msgs) == 0

    async def test_collect_visible_merges_parent_and_own(self):
        """After rewind + new turn, collect_visible shows parent + own messages."""
        store = SQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "original")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]

        result = rewind(store, session.session_id, user_snapshots[0].checkpoint_id)
        new_branch_id = result.new_branch_id

        await _run_agent(store, session.session_id, new_branch_id, "new direction")

        new_branch = store.get_branch(new_branch_id)
        assert new_branch is not None
        all_msgs = collect_branch_messages(store, new_branch)

        user_contents = [m.content for m in all_msgs if m.role == "user"]
        assert "original" in user_contents
        assert "new direction" in user_contents

    async def test_resume_after_rewind(self):
        """Resume on rewind branch returns correct merged context."""
        store = SQLiteTimelineStore(":memory:")
        session = create_session_with_default_branch(store)
        branch_id = session.active_branch_id

        await _run_agent(store, session.session_id, branch_id, "turn1")
        await _run_agent(store, session.session_id, branch_id, "turn2")

        checkpoints = store.get_checkpoints_by_branch(branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]

        result = rewind(store, session.session_id, user_snapshots[0].checkpoint_id)
        new_branch_id = result.new_branch_id

        await _run_agent(store, session.session_id, new_branch_id, "diverged")

        resume_result = resume(store, session.session_id)
        user_contents = [m.content for m in resume_result.messages if m.role == "user"]
        assert "turn1" in user_contents
        assert "diverged" in user_contents
        assert "turn2" not in user_contents
