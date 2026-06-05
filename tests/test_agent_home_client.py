import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from agent.config.settings import AgentHomeSettings, Settings
from agent.home.client import AgentHomeClient, AgentHomeError, initialize_agent_home
from agent.timeline.models import AgentRun, Branch, Checkpoint, CheckpointKind, Message, RunStatus, Session


class FakeTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.sessions: dict[str, dict] = {}
        self.branches: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}
        self.checkpoints: dict[str, dict] = {}
        self.memories: dict[str, dict] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/v1/agents":
            return httpx.Response(201, json={"agent_id": "l-agent:test", "token": "tok", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
        if request.method == "GET" and request.url.path == "/v1/agents/l-agent:test":
            auth = request.headers.get("Authorization")
            if auth == "Bearer tok":
                return httpx.Response(200, json={"agent_id": "l-agent:test", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
            return httpx.Response(401, json={"error": {"code": "auth_failed", "message": "bad", "details": {}}})
        if request.method == "POST" and request.url.path == "/v1/agents/l-agent:test/workspace/commands":
            return httpx.Response(200, json={"exit_code": 0, "stdout": "", "stderr": "", "changed_paths": []})
        if "/memory" in request.url.path:
            return self._handle_memory(request)
        return self._handle_timeline(request)

    def _handle_memory(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        prefix = "/v1/agents/l-agent:test"
        if request.method == "POST" and path == f"{prefix}/memory":
            memory_id = f"mem-{len(self.memories) + 1}"
            memory = {"memory_id": memory_id, **body}
            self.memories[memory_id] = memory
            return httpx.Response(200, json=memory)
        if request.method == "GET" and path == f"{prefix}/memory/search":
            query = request.url.params.get("q", "").lower()
            memories = [memory for memory in self.memories.values() if query in memory.get("content", "").lower()]
            return httpx.Response(200, json=memories)
        if request.method == "PATCH" and path.startswith(f"{prefix}/memory/"):
            memory_id = path.rsplit("/", 1)[-1]
            self.memories[memory_id].update(body)
            return httpx.Response(200, json=self.memories[memory_id])
        if request.method == "DELETE" and path.startswith(f"{prefix}/memory/"):
            self.memories.pop(path.rsplit("/", 1)[-1], None)
            return httpx.Response(204)
        if request.method == "POST" and path == f"{prefix}/memory/extractions":
            return httpx.Response(200, json={**body, "status": "queued"})
        return self._not_found()

    def _handle_timeline(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        prefix = "/v1/agents/l-agent:test"

        if request.method == "POST" and path == f"{prefix}/sessions":
            branch_id = f"b-{body['session_id']}"
            session = {"session_id": body["session_id"], "agent_id": "l-agent:test", "title": body.get("title", ""), "active_branch_id": branch_id, "metadata": body.get("metadata", {})}
            self.sessions[body["session_id"]] = session
            self.branches[branch_id] = {"branch_id": branch_id, "session_id": body["session_id"], "parent_branch_id": "", "fork_checkpoint_id": "", "base_message_cursor": 0, "resume_head": ""}
            return httpx.Response(200, json=session)
        if request.method == "GET" and path == f"{prefix}/sessions":
            return httpx.Response(200, json=list(self.sessions.values()))
        if request.method == "GET" and path.startswith(f"{prefix}/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            if session_id not in self.sessions:
                return self._not_found("session_not_found")
            return httpx.Response(200, json=self.sessions[session_id])
        if request.method == "PATCH" and path.startswith(f"{prefix}/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            if session_id not in self.sessions:
                return self._not_found("session_not_found")
            self.sessions[session_id].update({k: v for k, v in body.items() if v is not None})
            return httpx.Response(200, json=self.sessions[session_id])

        if request.method == "POST" and "/sessions/" in path and path.endswith("/branches"):
            session_id = path.split("/sessions/", 1)[1].split("/", 1)[0]
            branch = {"branch_id": body["branch_id"], "session_id": session_id, "parent_branch_id": body.get("parent_branch_id", ""), "fork_checkpoint_id": body.get("fork_checkpoint_id", ""), "base_message_cursor": body.get("base_message_cursor", 0), "resume_head": ""}
            self.branches[body["branch_id"]] = branch
            return httpx.Response(200, json=branch)
        if request.method == "GET" and path.startswith(f"{prefix}/branches/") and path.endswith("/messages/latest-sequence"):
            branch_id = path.split("/branches/", 1)[1].split("/", 1)[0]
            seqs = [m["sequence"] for m in self.messages.values() if m["branch_id"] == branch_id]
            return httpx.Response(200, json={"sequence": max(seqs) if seqs else -1})
        if request.method == "GET" and path.startswith(f"{prefix}/branches/") and path.endswith("/messages"):
            branch_id = path.split("/branches/", 1)[1].split("/", 1)[0]
            messages = [m for m in self.messages.values() if m["branch_id"] == branch_id]
            start = int(request.url.params.get("start", "0"))
            end = request.url.params.get("end")
            if end is None:
                messages = [m for m in messages if m["sequence"] >= start]
            else:
                messages = [m for m in messages if start <= m["sequence"] <= int(end)]
            messages.sort(key=lambda m: m["sequence"])
            return httpx.Response(200, json=messages)
        if request.method == "GET" and path.startswith(f"{prefix}/branches/") and path.endswith("/checkpoints"):
            branch_id = path.split("/branches/", 1)[1].split("/", 1)[0]
            checkpoints = [c for c in self.checkpoints.values() if c["branch_id"] == branch_id]
            checkpoints.sort(key=lambda c: c["checkpoint_id"])
            return httpx.Response(200, json=checkpoints)
        if request.method == "GET" and path.startswith(f"{prefix}/branches/") and path.endswith("/runs/latest"):
            branch_id = path.split("/branches/", 1)[1].split("/", 1)[0]
            for run in reversed(list(self.runs.values())):
                if run["branch_id"] == branch_id:
                    return httpx.Response(200, json=run)
            return self._not_found("run_not_found")
        if request.method == "GET" and path.startswith(f"{prefix}/branches/"):
            branch_id = path.rsplit("/", 1)[-1]
            if branch_id not in self.branches:
                return self._not_found("branch_not_found")
            return httpx.Response(200, json=self.branches[branch_id])
        if request.method == "PATCH" and path.startswith(f"{prefix}/branches/"):
            branch_id = path.rsplit("/", 1)[-1]
            if branch_id not in self.branches:
                return self._not_found("branch_not_found")
            self.branches[branch_id].update(body)
            return httpx.Response(200, json=self.branches[branch_id])

        if request.method == "POST" and path == f"{prefix}/runs":
            run = {"run_id": body["run_id"], "agent_id": "l-agent:test", "session_id": body["session_id"], "branch_id": body["branch_id"], "status": "running"}
            self.runs[run["run_id"]] = run
            return httpx.Response(200, json=run)
        if request.method == "GET" and path.startswith(f"{prefix}/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            if run_id not in self.runs:
                return self._not_found("run_not_found")
            return httpx.Response(200, json=self.runs[run_id])
        if request.method == "PATCH" and path.startswith(f"{prefix}/runs/") and path.endswith("/status"):
            run_id = path.split("/runs/", 1)[1].split("/", 1)[0]
            if run_id not in self.runs:
                return self._not_found("run_not_found")
            self.runs[run_id]["status"] = body["status"]
            return httpx.Response(200, json=self.runs[run_id])

        if request.method == "POST" and path == f"{prefix}/messages":
            sequence = len([m for m in self.messages.values() if m["branch_id"] == body["branch_id"]])
            message = {**body, "agent_id": "l-agent:test", "sequence": sequence}
            self.messages[body["message_id"]] = message
            return httpx.Response(200, json=message)

        if request.method == "POST" and path == f"{prefix}/checkpoints":
            checkpoint = {**body, "agent_id": "l-agent:test", "metadata": body.get("metadata", {})}
            self.checkpoints[body["checkpoint_id"]] = checkpoint
            return httpx.Response(200, json=checkpoint)
        if request.method == "GET" and path.startswith(f"{prefix}/checkpoints/"):
            checkpoint_id = path.rsplit("/", 1)[-1]
            if checkpoint_id not in self.checkpoints:
                return self._not_found("checkpoint_not_found")
            return httpx.Response(200, json=self.checkpoints[checkpoint_id])

        return self._not_found()

    @staticmethod
    def _not_found(code: str = "not_found") -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": code, "message": "missing", "details": {}}})


def test_initialize_creates_agent_and_writes_credentials(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("agent_home:\n  agent_id: l-agent:test\n  token: ''\n", encoding="utf-8")
    settings = Settings(agent_home=AgentHomeSettings(agent_id="l-agent:test", token=""), config_dir=tmp_path)
    transport = FakeTransport()

    client = initialize_agent_home(settings, config_path=config_path, transport=transport)

    assert client.agent_id == "l-agent:test"
    assert client.token == "tok"
    written = config_path.read_text(encoding="utf-8")
    assert "agent_id: l-agent:test" in written
    assert "token: tok" in written


def test_existing_token_is_verified(tmp_path: Path):
    settings = Settings(agent_home=AgentHomeSettings(agent_id="l-agent:test", token="tok"), config_dir=tmp_path)
    transport = FakeTransport()

    client = initialize_agent_home(settings, config_path=None, transport=transport)

    assert client.agent_id == "l-agent:test"
    assert transport.requests[-1].method == "GET"


def test_agent_home_error_parses_structured_error():
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="bad", transport=FakeTransport())

    with pytest.raises(AgentHomeError) as exc:
        client.verify_agent()

    assert exc.value.code == "auth_failed"
    assert exc.value.message == "bad"


def test_initialize_without_config_path_does_not_create_orphan_agent(tmp_path: Path):
    settings = Settings(agent_home=AgentHomeSettings(agent_id="l-agent:test", token=""), config_dir=tmp_path)
    transport = FakeTransport()

    with pytest.raises(AgentHomeError) as exc:
        initialize_agent_home(settings, config_path=None, transport=transport)

    assert exc.value.code == "agent_home_config_missing"
    assert transport.requests == []


def test_agent_home_client_closes_http_client_on_context_exit():
    with AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=FakeTransport()) as client:
        assert not client._client.is_closed

    assert client._client.is_closed


def test_workspace_run_command_passes_http_timeout_with_buffer():
    transport = FakeTransport()
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=transport)

    client.workspace_run_command("sleep 60", timeout_seconds=60)

    assert transport.requests[-1].extensions["timeout"]["connect"] == 65


def test_timeline_session_run_message_checkpoint_round_trip():
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=FakeTransport())
    session = Session(session_id="s1", title="Title", metadata={"k": "v"})

    client.create_session(session)
    loaded = client.get_session("s1")
    assert loaded is not None
    branch_id = loaded.active_branch_id
    client.create_run(AgentRun(run_id="r1", session_id="s1", branch_id=branch_id))
    client.append_message(Message(message_id="m1", session_id="s1", branch_id=branch_id, run_id="r1", sequence=0, role="user", content="hello"))
    client.create_checkpoint(Checkpoint(checkpoint_id="c1", session_id="s1", branch_id=branch_id, run_id="r1", kind=CheckpointKind.user_snapshot, name="snap", message_cursor=0))

    assert loaded.session_id == "s1"
    assert loaded.title == "Title"
    assert loaded.metadata == {"k": "v"}
    assert client.get_branch(branch_id) is not None
    assert client.get_run("r1") is not None
    assert client.get_latest_sequence(branch_id) == 0
    assert client.get_messages_by_branch(branch_id)[0].content == "hello"
    latest_stable = client.get_latest_stable_checkpoint(branch_id)
    assert client.get_checkpoint("c1") is not None
    assert client.get_checkpoints_by_branch(branch_id)[0].checkpoint_id == "c1"
    assert latest_stable is not None
    assert latest_stable.checkpoint_id == "c1"


def test_latest_stable_checkpoint_uses_highest_message_cursor():
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=FakeTransport())
    client.create_session(Session(session_id="s1"))
    loaded = client.get_session("s1")
    assert loaded is not None
    branch_id = loaded.active_branch_id
    client.create_run(AgentRun(run_id="r1", session_id="s1", branch_id=branch_id))
    client.append_message(Message(message_id="m1", session_id="s1", branch_id=branch_id, run_id="r1", sequence=0, role="user", content="first"))
    client.append_message(Message(message_id="m2", session_id="s1", branch_id=branch_id, run_id="r1", sequence=1, role="user", content="second"))
    client.create_checkpoint(Checkpoint(checkpoint_id="z-old", session_id="s1", branch_id=branch_id, run_id="r1", kind=CheckpointKind.user_snapshot, name="old", message_cursor=0))
    client.create_checkpoint(Checkpoint(checkpoint_id="a-new", session_id="s1", branch_id=branch_id, run_id="r1", kind=CheckpointKind.user_snapshot, name="new", message_cursor=1))

    checkpoint = client.get_latest_stable_checkpoint(branch_id)

    assert checkpoint is not None
    assert checkpoint.checkpoint_id == "a-new"


def test_update_run_status_and_get_latest_run_by_branch_returns_completed_status():
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=FakeTransport())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    client.create_session(Session(session_id="s1", active_branch_id="b1", created_at=now, updated_at=now))
    client.create_branch(Branch(branch_id="b1", session_id="s1", created_at=now))
    client.create_run(AgentRun(run_id="r1", session_id="s1", branch_id="b1", created_at=now))

    client.update_run_status("r1", RunStatus.completed)

    run = client.get_latest_run_by_branch("b1")
    assert run is not None
    assert run.status == RunStatus.completed


def test_memory_adapter_uses_agent_home_memory_endpoints():
    transport = FakeTransport()
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=transport)

    created = client.create_memory("preference", "Use python3", tags=["python"], source_session_id="s1", source_message_ids=["m1"], confidence=0.8)
    found = client.search_memory("python", type="preference", tags=["python"])
    updated = client.update_memory(created["memory_id"], content="Use python3 always", tags=["python", "cli"])
    extracted = client.extract_memory("s1", "manual")
    client.delete_memory(created["memory_id"])

    assert created["content"] == "Use python3"
    assert found == [created]
    assert updated["content"] == "Use python3 always"
    assert extracted == {"session_id": "s1", "trigger": "manual", "status": "queued"}
    requests = transport.requests[-5:]
    methods_and_paths = [(request.method, request.url.path) for request in requests]
    assert methods_and_paths == [
        ("POST", "/v1/agents/l-agent:test/memory"),
        ("GET", "/v1/agents/l-agent:test/memory/search"),
        ("PATCH", "/v1/agents/l-agent:test/memory/mem-1"),
        ("POST", "/v1/agents/l-agent:test/memory/extractions"),
        ("DELETE", "/v1/agents/l-agent:test/memory/mem-1"),
    ]
    assert json.loads(requests[0].content.decode("utf-8")) == {
        "type": "preference",
        "content": "Use python3",
        "tags": ["python"],
        "source_session_id": "s1",
        "source_message_ids": ["m1"],
        "confidence": 0.8,
    }
    assert dict(requests[1].url.params) == {"q": "python", "type": "preference", "tags": "python"}
    assert json.loads(requests[2].content.decode("utf-8")) == {"content": "Use python3 always", "tags": ["python", "cli"]}
    assert json.loads(requests[3].content.decode("utf-8")) == {"session_id": "s1", "trigger": "manual"}
