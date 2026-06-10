from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings, write_agent_home_credentials
from agent.timeline.models import AgentRun, Branch, Checkpoint, CheckpointKind, Message, RunStatus, Session
from agent.timeline.store import TimelineStore


@dataclass
class AgentHomeError(Exception):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class AgentHomeClient(TimelineStore):
    def __init__(self, base_url: str, agent_id: str, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.token = token
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=30.0)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AgentHomeClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, headers=self.headers, **kwargs)
        if response.status_code >= 400:
            self._raise_error(response)
        return response

    def _raise_error(self, response: httpx.Response) -> None:
        try:
            body = response.json()
        except ValueError:
            raise AgentHomeError("agent_home_error", response.text, {})
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            raise AgentHomeError(error.get("code", "agent_home_error"), error.get("message", "Agent-Home error"), error.get("details", {}))
        raise AgentHomeError("agent_home_error", response.text, {})

    def verify_agent(self) -> dict[str, Any]:
        return self._request("GET", f"/v1/agents/{self.agent_id}").json()

    def create_agent(self) -> str:
        response = self._client.post("/v1/agents", json={"agent_id": self.agent_id})
        if response.status_code >= 400:
            self._raise_error(response)
        token = response.json()["token"]
        self.token = token
        return token

    # --- Workspace adapter ---
    def workspace_put(self, path: str, content: str | bytes) -> dict[str, Any]:
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/workspace/files/write",
            json={"path": path, "content": content},
        ).json()

    def workspace_get_bytes(self, path: str) -> bytes:
        body = self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/workspace/files/read",
            json={"path": path},
        ).json()
        return body["content"].encode("utf-8")

    def workspace_get_text(self, path: str) -> str:
        body = self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/workspace/files/read",
            json={"path": path},
        ).json()
        return body["content"]

    def workspace_list(self, prefix: str = "/") -> list[dict[str, Any]]:
        body = self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/workspace/files/list",
            json={"path": prefix},
        ).json()
        return body["entries"]

    def workspace_run_command(self, command: str, timeout_seconds: int = 120, env: dict[str, str] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/workspace/commands",
            json={"command": command, "timeout_seconds": timeout_seconds, "env": env or {}},
            timeout=timeout_seconds + 5,
        ).json()

    # --- Memory adapter ---
    def search_memory(self, q: str, type: str | None = None, tags: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"q": q}
        if type is not None:
            params["type"] = type
        if tags is not None:
            params["tags"] = ",".join(tags)
        return self._request("GET", f"/v1/agents/{self.agent_id}/memory/search", params=params).json()

    def create_memory(
        self,
        type: str,
        content: str,
        tags: list[str] | None = None,
        source_session_id: str = "",
        source_message_ids: list[str] | None = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/memory",
            json={
                "type": type,
                "content": content,
                "tags": tags or [],
                "source_session_id": source_session_id,
                "source_message_ids": source_message_ids or [],
                "confidence": confidence,
            },
        ).json()

    def update_memory(self, memory_id: str, content: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if content is not None:
            body["content"] = content
        if tags is not None:
            body["tags"] = tags
        return self._request("PATCH", f"/v1/agents/{self.agent_id}/memory/{memory_id}", json=body).json()

    def delete_memory(self, memory_id: str) -> None:
        self._request("DELETE", f"/v1/agents/{self.agent_id}/memory/{memory_id}")

    def extract_memory(self, session_id: str, trigger: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/agents/{self.agent_id}/memory/extractions",
            json={"session_id": session_id, "trigger": trigger},
        ).json()

    # --- TimelineStore adapter ---
    def create_session(self, session: Session) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/sessions", json={"session_id": session.session_id, "title": session.title, "metadata": session.metadata})

    def get_session(self, session_id: str) -> Session | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/sessions/{session_id}").json()
        except AgentHomeError as exc:
            if exc.code in {"not_found", "session_not_found"}:
                return None
            raise
        return self._json_to_session(body)

    def update_session(self, session: Session) -> None:
        self._request("PATCH", f"/v1/agents/{self.agent_id}/sessions/{session.session_id}", json={"title": session.title, "metadata": session.metadata, "active_branch_id": session.active_branch_id})

    def list_sessions(self) -> list[Session]:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/sessions").json()
        return [self._json_to_session(item) for item in body]

    def create_branch(self, branch: Branch) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/sessions/{branch.session_id}/branches", json={"branch_id": branch.branch_id, "parent_branch_id": branch.parent_branch_id, "fork_checkpoint_id": branch.fork_checkpoint_id, "base_message_cursor": branch.base_message_cursor})

    def get_branch(self, branch_id: str) -> Branch | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}").json()
        except AgentHomeError as exc:
            if exc.code in {"not_found", "branch_not_found"}:
                return None
            raise
        return self._json_to_branch(body)

    def update_branch(self, branch: Branch) -> None:
        self._request("PATCH", f"/v1/agents/{self.agent_id}/branches/{branch.branch_id}", json={"resume_head": branch.resume_head})

    def create_run(self, run: AgentRun) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/runs", json={"run_id": run.run_id, "session_id": run.session_id, "branch_id": run.branch_id})

    def get_run(self, run_id: str) -> AgentRun | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/runs/{run_id}").json()
        except AgentHomeError as exc:
            if exc.code in {"not_found", "run_not_found"}:
                return None
            raise
        return self._json_to_run(body)

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        try:
            self._request("PATCH", f"/v1/agents/{self.agent_id}/runs/{run_id}/status", json={"status": status.value})
        except AgentHomeError as exc:
            if exc.code in {"not_found", "run_not_found"}:
                return
            raise

    def get_latest_run_by_branch(self, branch_id: str) -> AgentRun | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/runs/latest").json()
        except AgentHomeError as exc:
            if exc.code in {"not_found", "run_not_found"}:
                return None
            raise
        return self._json_to_run(body)

    def append_message(self, message: Message) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/messages", json={"message_id": message.message_id, "session_id": message.session_id, "branch_id": message.branch_id, "run_id": message.run_id, "role": message.role, "content": message.content, "tool_call_id": message.tool_call_id, "tool_calls": message.tool_calls})

    def get_messages_by_branch(self, branch_id: str, start: int = 0, end: int | None = None) -> list[Message]:
        params: dict[str, int] = {"start": start}
        if end is not None:
            params["end"] = end
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/messages", params=params).json()
        return [self._json_to_message(item) for item in body]

    def get_latest_sequence(self, branch_id: str) -> int:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/messages/latest-sequence").json()
        return int(body["sequence"])

    def create_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/checkpoints", json={"checkpoint_id": checkpoint.checkpoint_id, "session_id": checkpoint.session_id, "branch_id": checkpoint.branch_id, "run_id": checkpoint.run_id, "kind": checkpoint.kind.value, "name": checkpoint.name, "message_cursor": checkpoint.message_cursor})

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/checkpoints/{checkpoint_id}").json()
        except AgentHomeError as exc:
            if exc.code in {"not_found", "checkpoint_not_found"}:
                return None
            raise
        return self._json_to_checkpoint(body)

    def get_checkpoints_by_branch(self, branch_id: str) -> list[Checkpoint]:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/checkpoints").json()
        return [self._json_to_checkpoint(item) for item in body]

    def get_latest_stable_checkpoint(self, branch_id: str) -> Checkpoint | None:
        checkpoints = [checkpoint for checkpoint in self.get_checkpoints_by_branch(branch_id) if checkpoint.kind == CheckpointKind.user_snapshot]
        return max(checkpoints, key=lambda checkpoint: checkpoint.message_cursor) if checkpoints else None

    @staticmethod
    def _str_to_dt(value: str | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _str_to_optional_dt(value: str | None) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _json_to_session(self, data: dict[str, Any]) -> Session:
        return Session(
            session_id=data["session_id"],
            title=data.get("title", ""),
            active_branch_id=data.get("active_branch_id", ""),
            created_at=self._str_to_dt(data.get("created_at")),
            updated_at=self._str_to_dt(data.get("updated_at")),
            metadata=data.get("metadata", {}),
        )

    def _json_to_branch(self, data: dict[str, Any]) -> Branch:
        return Branch(
            branch_id=data["branch_id"],
            session_id=data["session_id"],
            parent_branch_id=data.get("parent_branch_id", ""),
            fork_checkpoint_id=data.get("fork_checkpoint_id", ""),
            base_message_cursor=data.get("base_message_cursor", 0),
            resume_head=data.get("resume_head", ""),
            created_at=self._str_to_dt(data.get("created_at")),
        )

    def _json_to_run(self, data: dict[str, Any]) -> AgentRun:
        return AgentRun(
            run_id=data["run_id"],
            session_id=data["session_id"],
            branch_id=data["branch_id"],
            status=RunStatus(data.get("status", RunStatus.running.value)),
            created_at=self._str_to_dt(data.get("created_at")),
            completed_at=self._str_to_optional_dt(data.get("completed_at")),
        )

    def _json_to_message(self, data: dict[str, Any]) -> Message:
        return Message(
            message_id=data["message_id"],
            session_id=data["session_id"],
            branch_id=data["branch_id"],
            run_id=data["run_id"],
            sequence=data["sequence"],
            role=data["role"],
            content=data.get("content", ""),
            tool_call_id=data.get("tool_call_id", ""),
            tool_calls=data.get("tool_calls", []),
            created_at=self._str_to_dt(data.get("created_at")),
        )

    def _json_to_checkpoint(self, data: dict[str, Any]) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=data["checkpoint_id"],
            session_id=data["session_id"],
            branch_id=data["branch_id"],
            run_id=data["run_id"],
            kind=CheckpointKind(data["kind"]),
            name=data["name"],
            message_cursor=data.get("message_cursor", 0),
            created_at=self._str_to_dt(data.get("created_at")),
        )


def initialize_agent_home(settings: Settings, config_path: Path | None, transport: httpx.BaseTransport | None = None) -> AgentHomeClient:
    home = settings.agent_home
    client = AgentHomeClient(home.base_url, home.agent_id, home.token, transport=transport)
    if home.token:
        client.verify_agent()
        return client
    if not home.auto_create_agent:
        raise AgentHomeError("agent_home_token_missing", "agent_home.token is required when auto_create_agent is false", {})
    if config_path is None:
        raise AgentHomeError("agent_home_config_missing", "cannot persist Agent-Home token without a config path", {})
    token = client.create_agent()
    write_agent_home_credentials(config_path, token)
    return client
