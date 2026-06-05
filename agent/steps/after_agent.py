from __future__ import annotations

import uuid

from agent.core.context import RunContext
from agent.core.lifecycle import HookPhase
from agent.steps.base import Step
from agent.timeline.store import TimelineStore
from agent.timeline.models import Checkpoint, CheckpointKind, RunStatus


class AgentHomeRunFinalize(Step):
    """Finalize Agent Home state after a run ends."""

    def __init__(self, auto_extract_memory: bool = False) -> None:
        super().__init__("agent_home.run_finalize", HookPhase.after_agent)
        self.auto_extract_memory = auto_extract_memory

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None or not ctx.run_id:
            return
        status = RunStatus(ctx.status)
        store.update_run_status(ctx.run_id, status)
        if status == RunStatus.completed:
            self._update_resume_head(ctx, store)
        if self.auto_extract_memory and ctx.session_id:
            self._extract_memory(store, ctx.session_id)

    def _update_resume_head(self, ctx: RunContext, store: TimelineStore) -> None:
        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        run_checkpoints = [cp for cp in checkpoints if cp.run_id == ctx.run_id]
        if not run_checkpoints:
            return
        branch = store.get_branch(ctx.branch_id)
        if branch is None:
            return
        branch.resume_head = run_checkpoints[-1].checkpoint_id
        store.update_branch(branch)

    def _extract_memory(self, store, session_id: str) -> None:
        extract_memory = getattr(store, "extract_memory", None)
        if not callable(extract_memory):
            return
        try:
            extract_memory(session_id, "after_agent")
        except Exception as exc:
            if getattr(exc, "code", None) == "auto_extract_disabled":
                return
            raise


class RunMarkTerminalState(Step):
    """Update AgentRun status to completed/failed/interrupted."""

    def __init__(self) -> None:
        super().__init__("run.mark_terminal_state", HookPhase.after_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        status_map = {"completed": RunStatus.completed, "failed": RunStatus.failed, "interrupted": RunStatus.interrupted}
        status = status_map.get(ctx.status, RunStatus.failed)
        store.update_run_status(ctx.run_id, status)


class CheckpointRecordRunTerminalState(Step):
    """Create runtime checkpoint for run terminal state."""

    def __init__(self) -> None:
        super().__init__("checkpoint.record_run_terminal_state", HookPhase.after_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        cursor = store.get_latest_sequence(ctx.branch_id)
        name = f"run_{ctx.status}"
        cp = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            kind=CheckpointKind.runtime,
            name=name,
            message_cursor=cursor,
        )
        store.create_checkpoint(cp)


class BranchUpdateResumeHead(Step):
    """Update branch.resume_head when run completes successfully."""

    def __init__(self) -> None:
        super().__init__("branch.update_resume_head", HookPhase.after_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        if ctx.status != "completed":
            return
        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        run_completed_cp = None
        for cp in reversed(checkpoints):
            if cp.run_id == ctx.run_id and cp.name == "run_completed":
                run_completed_cp = cp
                break
        if run_completed_cp is None:
            return
        branch = store.get_branch(ctx.branch_id)
        if branch is None:
            return
        branch.resume_head = run_completed_cp.checkpoint_id
        store.update_branch(branch)
