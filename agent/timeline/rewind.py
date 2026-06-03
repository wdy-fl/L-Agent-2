from __future__ import annotations

import uuid
from dataclasses import dataclass

from agent.timeline.models import Branch, CheckpointKind, Message
from agent.timeline.resume import collect_branch_messages
from agent.timeline.store import TimelineStore


@dataclass
class RewindResult:
    new_branch_id: str
    messages: list[Message]


def rewind(store: TimelineStore, session_id: str, checkpoint_id: str) -> RewindResult:
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"session {session_id} not found")

    checkpoint = store.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise ValueError(f"checkpoint {checkpoint_id} not found")
    if checkpoint.kind != CheckpointKind.user_snapshot:
        raise ValueError(f"checkpoint {checkpoint_id} is not a user_snapshot, cannot rewind to it")

    parent_branch_id = checkpoint.branch_id
    new_branch_id = str(uuid.uuid4())

    new_branch = Branch(
        branch_id=new_branch_id,
        session_id=session_id,
        parent_branch_id=parent_branch_id,
        fork_checkpoint_id=checkpoint_id,
        base_message_cursor=checkpoint.message_cursor,
    )
    store.create_branch(new_branch)

    session.active_branch_id = new_branch_id
    store.update_session(session)

    messages = collect_branch_messages(store, new_branch)

    return RewindResult(new_branch_id=new_branch_id, messages=messages)
