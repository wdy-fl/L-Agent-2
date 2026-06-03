from __future__ import annotations

from dataclasses import dataclass

from agent.timeline.models import Branch, Checkpoint, Message, RunStatus
from agent.timeline.store import TimelineStore


@dataclass
class ResumeResult:
    session_id: str
    branch_id: str
    messages: list[Message]
    interrupted_info: str | None = None


def collect_branch_messages(store: TimelineStore, branch: Branch, up_to_cursor: int | None = None) -> list[Message]:
    if branch.parent_branch_id:
        parent = store.get_branch(branch.parent_branch_id)
        if parent:
            parent_msgs = store.get_messages_by_branch(
                parent.branch_id, start=0, end=branch.base_message_cursor
            )
        else:
            parent_msgs = []
    else:
        parent_msgs = []

    if up_to_cursor is not None:
        own_msgs = store.get_messages_by_branch(branch.branch_id, start=0, end=up_to_cursor)
    else:
        own_msgs = store.get_messages_by_branch(branch.branch_id)

    return parent_msgs + own_msgs


def resume(store: TimelineStore, session_id: str) -> ResumeResult:
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"session {session_id} not found")

    branch = store.get_branch(session.active_branch_id)
    if branch is None:
        raise ValueError(f"active branch {session.active_branch_id} not found")

    interrupted_info: str | None = None

    if branch.resume_head:
        checkpoint = _get_checkpoint(store, branch.branch_id, branch.resume_head)
        if checkpoint:
            messages = collect_branch_messages(store, branch, up_to_cursor=checkpoint.message_cursor)
        else:
            messages = collect_branch_messages(store, branch)
    else:
        messages = collect_branch_messages(store, branch)

    latest_run = store.get_latest_run_by_branch(branch.branch_id)
    if latest_run and latest_run.status == RunStatus.interrupted:
        interrupted_info = f"上次运行中断（run_id={latest_run.run_id}）"

    return ResumeResult(
        session_id=session_id,
        branch_id=branch.branch_id,
        messages=messages,
        interrupted_info=interrupted_info,
    )


def _get_checkpoint(store: TimelineStore, branch_id: str, checkpoint_id: str) -> Checkpoint | None:
    checkpoints = store.get_checkpoints_by_branch(branch_id)
    for cp in checkpoints:
        if cp.checkpoint_id == checkpoint_id:
            return cp
    return None
