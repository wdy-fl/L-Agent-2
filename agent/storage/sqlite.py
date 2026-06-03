from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agent.storage.schema import SCHEMA_SQL
from agent.timeline.models import (
    AgentRun,
    Branch,
    Checkpoint,
    CheckpointKind,
    Message,
    RunStatus,
    Session,
)
from agent.timeline.store import TimelineStore


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class SQLiteTimelineStore(TimelineStore):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)

    # --- Session ---
    def create_session(self, session: Session) -> None:
        self._conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            (session.session_id, session.title, session.active_branch_id,
             _dt_to_str(session.created_at), _dt_to_str(session.updated_at),
             json.dumps(session.metadata)),
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        return Session(
            session_id=row["session_id"], title=row["title"],
            active_branch_id=row["active_branch_id"],
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
            metadata=json.loads(row["metadata"]),
        )

    def update_session(self, session: Session) -> None:
        self._conn.execute(
            "UPDATE sessions SET title=?, active_branch_id=?, updated_at=?, metadata=? WHERE session_id=?",
            (session.title, session.active_branch_id, _dt_to_str(session.updated_at),
             json.dumps(session.metadata), session.session_id),
        )
        self._conn.commit()

    # --- Branch ---
    def create_branch(self, branch: Branch) -> None:
        self._conn.execute(
            "INSERT INTO branches VALUES (?,?,?,?,?,?,?)",
            (branch.branch_id, branch.session_id, branch.parent_branch_id,
             branch.fork_checkpoint_id, branch.base_message_cursor,
             branch.resume_head, _dt_to_str(branch.created_at)),
        )
        self._conn.commit()

    def get_branch(self, branch_id: str) -> Branch | None:
        row = self._conn.execute("SELECT * FROM branches WHERE branch_id=?", (branch_id,)).fetchone()
        if not row:
            return None
        return Branch(
            branch_id=row["branch_id"], session_id=row["session_id"],
            parent_branch_id=row["parent_branch_id"],
            fork_checkpoint_id=row["fork_checkpoint_id"],
            base_message_cursor=row["base_message_cursor"],
            resume_head=row["resume_head"],
            created_at=_str_to_dt(row["created_at"]),
        )

    def update_branch(self, branch: Branch) -> None:
        self._conn.execute(
            "UPDATE branches SET parent_branch_id=?, fork_checkpoint_id=?, base_message_cursor=?, resume_head=? WHERE branch_id=?",
            (branch.parent_branch_id, branch.fork_checkpoint_id,
             branch.base_message_cursor, branch.resume_head, branch.branch_id),
        )
        self._conn.commit()

    # --- AgentRun ---
    def create_run(self, run: AgentRun) -> None:
        self._conn.execute(
            "INSERT INTO agent_runs VALUES (?,?,?,?,?,?)",
            (run.run_id, run.session_id, run.branch_id, run.status.value,
             _dt_to_str(run.created_at), None),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> AgentRun | None:
        row = self._conn.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return AgentRun(
            run_id=row["run_id"], session_id=row["session_id"],
            branch_id=row["branch_id"], status=RunStatus(row["status"]),
            created_at=_str_to_dt(row["created_at"]),
            completed_at=_str_to_dt(row["completed_at"]) if row["completed_at"] else None,
        )

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        completed_at = _dt_to_str(datetime.now(timezone.utc)) if status != RunStatus.running else None
        self._conn.execute(
            "UPDATE agent_runs SET status=?, completed_at=? WHERE run_id=?",
            (status.value, completed_at, run_id),
        )
        self._conn.commit()

    # --- Message ---
    def append_message(self, message: Message) -> None:
        self._conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)",
            (message.message_id, message.session_id, message.branch_id,
             message.run_id, message.sequence, message.role, message.content,
             message.tool_call_id, json.dumps(message.tool_calls),
             _dt_to_str(message.created_at)),
        )
        self._conn.commit()

    def get_messages_by_branch(self, branch_id: str, start: int = 0, end: int | None = None) -> list[Message]:
        if end is not None:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE branch_id=? AND sequence>=? AND sequence<=? ORDER BY sequence",
                (branch_id, start, end),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE branch_id=? AND sequence>=? ORDER BY sequence",
                (branch_id, start),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_latest_sequence(self, branch_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(sequence) as max_seq FROM messages WHERE branch_id=?", (branch_id,)
        ).fetchone()
        val = row["max_seq"] if row else None
        return val if val is not None else -1

    # --- Checkpoint ---
    def create_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._conn.execute(
            "INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?,?)",
            (checkpoint.checkpoint_id, checkpoint.session_id, checkpoint.branch_id,
             checkpoint.run_id, checkpoint.kind.value, checkpoint.name,
             checkpoint.message_cursor, _dt_to_str(checkpoint.created_at)),
        )
        self._conn.commit()

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
        ).fetchone()
        return self._row_to_checkpoint(row) if row else None

    def get_checkpoints_by_branch(self, branch_id: str) -> list[Checkpoint]:
        rows = self._conn.execute(
            "SELECT * FROM checkpoints WHERE branch_id=? ORDER BY created_at", (branch_id,)
        ).fetchall()
        return [self._row_to_checkpoint(r) for r in rows]

    def get_latest_stable_checkpoint(self, branch_id: str) -> Checkpoint | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE branch_id=? AND kind='user_snapshot' ORDER BY created_at DESC LIMIT 1",
            (branch_id,),
        ).fetchone()
        return self._row_to_checkpoint(row) if row else None

    # --- Query helpers ---
    def get_latest_run_by_branch(self, branch_id: str) -> AgentRun | None:
        row = self._conn.execute(
            "SELECT * FROM agent_runs WHERE branch_id=? ORDER BY created_at DESC LIMIT 1",
            (branch_id,),
        ).fetchone()
        if not row:
            return None
        return AgentRun(
            run_id=row["run_id"], session_id=row["session_id"],
            branch_id=row["branch_id"], status=RunStatus(row["status"]),
            created_at=_str_to_dt(row["created_at"]),
            completed_at=_str_to_dt(row["completed_at"]) if row["completed_at"] else None,
        )

    # --- helpers ---
    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        return Message(
            message_id=row["message_id"], session_id=row["session_id"],
            branch_id=row["branch_id"], run_id=row["run_id"],
            sequence=row["sequence"], role=row["role"],
            content=row["content"], tool_call_id=row["tool_call_id"],
            tool_calls=json.loads(row["tool_calls"]),
            created_at=_str_to_dt(row["created_at"]),
        )

    @staticmethod
    def _row_to_checkpoint(row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"], session_id=row["session_id"],
            branch_id=row["branch_id"], run_id=row["run_id"],
            kind=CheckpointKind(row["kind"]), name=row["name"],
            message_cursor=row["message_cursor"],
            created_at=_str_to_dt(row["created_at"]),
        )
