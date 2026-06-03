from __future__ import annotations

import uuid

from agent.timeline.models import Branch, Session
from agent.timeline.store import TimelineStore


def create_session_with_default_branch(
    store: TimelineStore,
    session_id: str | None = None,
    title: str = "",
) -> Session:
    session_id = session_id or str(uuid.uuid4())
    branch_id = str(uuid.uuid4())

    branch = Branch(branch_id=branch_id, session_id=session_id)
    session = Session(session_id=session_id, title=title, active_branch_id=branch_id)

    store.create_session(session)
    store.create_branch(branch)
    return session
