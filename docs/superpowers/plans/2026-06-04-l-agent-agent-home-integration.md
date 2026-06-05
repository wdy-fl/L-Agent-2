# L-Agent Agent-Home Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 L-Agent 的 timeline、workspace、memory 和 terminal 主路径全部接入 Agent-Home，本地 SQLite timeline、本地文件工具和本地 terminal 不再作为 CLI 主路径使用。

**Architecture:** 新增 L-Agent `AgentHomeClient` 作为唯一状态访问入口，并适配现有 `TimelineStore` 方法以减少 runner/step 改动。Agent-Home 补充 workspace command execution API，负责在每个 `agent_id` 的 execution root 内执行 terminal 命令并把文件变更同步回逻辑 workspace。L-Agent CLI 启动时自动初始化稳定 `agent_id + token`，但不托管 Agent-Home daemon 生命周期。

**Tech Stack:** Python 3.11+, httpx, Typer, Rich, FastAPI, SQLite stdlib, pytest, pytest-asyncio.

---

## Execution Status

- 执行方式：Subagent-Driven Development。
- 隔离工作区：
  - `Agent-Home/.worktrees/agent-home-integration`
  - `L-Agent/.worktrees/agent-home-integration`
- 基线测试：Agent-Home `35 passed`，L-Agent `100 passed`。
- 当前进度：
  - Task 1 `Agent-Home Workspace Command API`：已实现、已补充质量修复、已通过规格审查和代码质量审查；尚未提交 commit。
  - Task 2 `Agent-Home Timeline Compatibility API`：已实现、已补齐负向测试、已通过规格审查和代码质量审查；尚未提交 commit。
  - Task 3 `L-Agent Agent-Home Settings and Auto Initialization`：已实现、已补充质量修复、已通过规格审查和代码质量审查；尚未提交 commit。
  - Task 4 `AgentHomeClient Timeline Adapter`：已实现、已通过规格审查和代码质量复审；尚未提交 commit。
  - Task 5 `Run Finalization Step`：已实现、已通过规格审查和代码质量复审；尚未提交 commit。
  - Task 7 `Memory Search, Prefetch, and CLI Commands`：已实现、已补充复审要求的覆盖测试、已通过规格审查和代码质量复审；尚未提交 commit。
  - Task 8 `CLI Main Path Migration`：已实现、已补充代码质量复审要求的生命周期和配置路径测试、已通过规格审查和代码质量复审；尚未提交 commit。
  - Task 9-10：未开始。
- 最近验证：
  - Task 1：`tests/test_workspace_command.py`、`tests/test_workspace.py` 通过；相关 Pyright 诊断清零。
  - Task 2：`tests/test_timeline_compat.py`、`tests/test_timeline.py`、`tests/test_resume_rewind.py` 通过；相关 Pyright 诊断清零。
  - Task 3：`tests/test_agent_home_client.py` 通过（`5 passed`）；规格审查通过；代码质量复审通过。
  - Task 4：`tests/test_agent_home_client.py` 通过（`8 passed`）；相关 Pyright 诊断清零；规格审查通过；代码质量复审通过。
  - Task 5：`tests/test_agent_home_memory.py`、`tests/test_lifecycle_steps.py` 通过（合计 `9 passed`）；相关 Pyright 诊断清零；规格审查通过；代码质量复审通过。
  - Task 7：`tests/test_agent_home_memory.py`、`tests/test_agent_home_client.py` 通过（合计 `22 passed`）；相关 Pyright 诊断清零；规格审查通过；代码质量复审通过。
  - Task 8：`tests/test_agent_home_cli.py`、`tests/test_agent_home_tools.py`、`tests/test_agent_home_memory.py` 通过（合计 `20 passed`）；相关 Pyright 诊断清零；规格审查通过；代码质量复审通过。

## Scope Check

本计划覆盖设计文档确认的单个集成目标：L-Agent 接入 Agent-Home。虽然涉及 timeline、workspace、memory、terminal 四条实现线，但它们共享同一个主路径切换目标：L-Agent 不再直接管理状态或绕过 workspace 沙箱。因此计划按可独立测试的垂直任务拆分，任务之间按顺序执行。

## File Structure

### Agent-Home

- Modify: `Agent-Home/agent_home/models.py` — 增加 command execution request/response model。
- Modify: `Agent-Home/agent_home/config.py` — 增加 `execution_root` 设置。
- Modify: `Agent-Home/agent_home/workspace.py` — 增加 workspace command execution API、materialize 和 sync 逻辑。
- Test: `Agent-Home/tests/test_workspace_command.py` — 验证 command 在 execution root 内运行并同步 workspace 变更。

### L-Agent

- Modify: `L-Agent/agent/config/settings.py` — 增加 `AgentHomeSettings`、稳定默认 `agent_id`、配置写回。
- Create: `L-Agent/agent/home/__init__.py` — 导出 Agent-Home client 类型。
- Create: `L-Agent/agent/home/client.py` — HTTP client、错误解析、自动初始化、timeline/workspace/memory 方法。
- Modify: `L-Agent/agent/core/context.py` — 增加 `home_client` 字段，保留 `timeline_store` 兼容字段。
- Modify: `L-Agent/agent/core/factory.py` — build runner 接收 client，注册 Agent-Home tools 和 memory/finalize steps。
- Modify: `L-Agent/agent/steps/before_agent.py` — MemoryPrefetch 改为 Agent-Home 查询。
- Create: `L-Agent/agent/steps/after_agent.py` — run status、resume_head、memory extraction 收尾。
- Modify: `L-Agent/agent/tools/builtin/file_ops.py` — 增加 Agent-Home 版本 file tools。
- Modify: `L-Agent/agent/tools/builtin/terminal.py` — 增加 Agent-Home 版本 terminal tool。
- Modify: `L-Agent/agent/tools/builtin/__init__.py` — registry 根据 client 注册沙箱工具。
- Modify: `L-Agent/agent/cli/app.py` — 初始化 AgentHomeClient，移除 SQLiteTimelineStore 主路径。
- Modify: `L-Agent/agent/cli/commands.py` — session/memory 命令改走 AgentHomeClient。
- Test: `L-Agent/tests/test_agent_home_client.py` — client 初始化、错误解析、timeline 方法。
- Test: `L-Agent/tests/test_agent_home_tools.py` — workspace file tools 和 terminal tool。
- Test: `L-Agent/tests/test_agent_home_cli.py` — CLI/session command 行为。
- Test: `L-Agent/tests/test_agent_home_memory.py` — memory prefetch 和 extraction 触发策略。

## Task 1: Agent-Home Workspace Command API

**Status:** Implemented in `Agent-Home/.worktrees/agent-home-integration`; spec review approved; code quality review approved; commit pending.

**Files:**
- Modify: `Agent-Home/agent_home/config.py`
- Modify: `Agent-Home/agent_home/models.py`
- Modify: `Agent-Home/agent_home/workspace.py`
- Test: `Agent-Home/tests/test_workspace_command.py`

- [x] **Step 1: Write failing command execution tests**

Create `Agent-Home/tests/test_workspace_command.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from agent_home.app import create_app
from agent_home.config import Settings


def make_client(tmp_path: Path):
    app = create_app(Settings(
        database_path=tmp_path / "state.sqlite",
        object_root=tmp_path / "objects",
        execution_root=tmp_path / "exec",
    ))
    client = TestClient(app)
    token = client.post("/v1/agents", json={"agent_id": "agent-a"}).json()["token"]
    return client, {"Authorization": f"Bearer {token}"}, tmp_path


def test_workspace_command_reads_existing_logical_file_and_writes_back_changes(tmp_path: Path):
    client, headers, root = make_client(tmp_path)
    client.put(
        "/v1/agents/agent-a/workspace/object",
        headers=headers,
        params={"path": "/notes/todo.md"},
        content=b"before",
    )

    response = client.post(
        "/v1/agents/agent-a/workspace/commands",
        headers=headers,
        json={"command": "cat notes/todo.md && printf '\nafter' >> notes/todo.md", "timeout_seconds": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 0
    assert "before" in body["stdout"]
    assert body["changed_paths"] == ["/notes/todo.md"]
    updated = client.get(
        "/v1/agents/agent-a/workspace/object",
        headers=headers,
        params={"path": "/notes/todo.md"},
    )
    assert updated.text == "before\nafter"
    assert not (root / "notes" / "todo.md").exists()


def test_workspace_command_new_file_is_synced_to_logical_workspace(tmp_path: Path):
    client, headers, _ = make_client(tmp_path)

    response = client.post(
        "/v1/agents/agent-a/workspace/commands",
        headers=headers,
        json={"command": "mkdir -p artifacts && printf '{\"ok\": true}' > artifacts/result.json"},
    )

    assert response.status_code == 200
    assert response.json()["changed_paths"] == ["/artifacts/result.json"]
    read = client.get(
        "/v1/agents/agent-a/workspace/object",
        headers=headers,
        params={"path": "/artifacts/result.json"},
    )
    assert read.text == '{"ok": true}'


def test_workspace_command_timeout_returns_structured_error(tmp_path: Path):
    client, headers, _ = make_client(tmp_path)

    response = client.post(
        "/v1/agents/agent-a/workspace/commands",
        headers=headers,
        json={"command": "python3 -c 'import time; time.sleep(2)'", "timeout_seconds": 1},
    )

    assert response.status_code == 408
    assert response.json()["error"]["code"] == "command_timeout"
```

- [x] **Step 2: Run test to verify it fails**

Run from `Agent-Home/`:

```bash
python3 -m pytest tests/test_workspace_command.py -v
```

Expected: FAIL because `Settings` has no `execution_root` and `/workspace/commands` does not exist.

- [x] **Step 3: Add config and models**

Modify `Agent-Home/agent_home/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("agent_home.sqlite")
    object_root: Path = Path(".agent-home/objects")
    execution_root: Path = Path(".agent-home/execution")


def default_settings() -> Settings:
    return Settings()
```

Append to `Agent-Home/agent_home/models.py`:

```python
class WorkspaceCommandRequest(BaseModel):
    command: str = Field(min_length=1)
    timeout_seconds: int = 120
    env: dict[str, str] = Field(default_factory=dict)


class WorkspaceCommandResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    changed_paths: list[str]
```

Modify `Agent-Home/agent_home/errors.py` and add these entries to `ERROR_STATUS`:

```python
    "command_timeout": 408,
    "command_failed": 400,
```

- [x] **Step 4: Implement command execution API**

Append this code to `Agent-Home/agent_home/workspace.py` after existing routes:

```python
import os
import shutil
import subprocess
from agent_home.models import WorkspaceCommandRequest, WorkspaceCommandResponse


def execution_root(request: Request, agent_id: str) -> Path:
    root = request.app.state.settings.execution_root / safe_agent_dir(agent_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _logical_path_from_exec_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return "/" + relative.as_posix()


def _materialize_workspace(agent_id: str, request: Request, root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    rows = storage(request)._conn.execute(
        """
        SELECT path, storage_key
        FROM workspace_objects
        WHERE agent_id = ? AND kind = 'file'
        ORDER BY path ASC
        """,
        (agent_id,),
    ).fetchall()
    object_dir = object_root(request, agent_id)
    for row in rows:
        logical_path = validate_path(row["path"])
        target = root / logical_path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(object_dir / row["storage_key"], target)


def _sync_workspace(agent_id: str, request: Request, root: Path) -> list[str]:
    changed_paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        logical_path = _logical_path_from_exec_path(root, path)
        body = path.read_bytes()
        current = storage(request)._conn.execute(
            """
            SELECT content_hash
            FROM workspace_objects
            WHERE agent_id = ? AND path = ?
            """,
            (agent_id, logical_path),
        ).fetchone()
        content_hash = hashlib.sha256(body).hexdigest()
        if current is not None and current["content_hash"] == content_hash:
            continue
        object_id = str(uuid4())
        storage_key = f"{object_id}.blob"
        blob_path = object_root(request, agent_id) / storage_key
        blob_path.write_bytes(body)
        with storage(request).transaction() as connection:
            old = connection.execute(
                """
                SELECT storage_key
                FROM workspace_objects
                WHERE agent_id = ? AND path = ?
                """,
                (agent_id, logical_path),
            ).fetchone()
            if old is None:
                connection.execute(
                    """
                    INSERT INTO workspace_objects(agent_id, object_id, path, kind, content_type, size, content_hash, storage_key, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (agent_id, object_id, logical_path, "file", "application/octet-stream", len(body), content_hash, storage_key, json.dumps({})),
                )
            else:
                connection.execute(
                    """
                    UPDATE workspace_objects
                    SET object_id = ?, size = ?, content_hash = ?, storage_key = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE agent_id = ? AND path = ?
                    """,
                    (object_id, len(body), content_hash, storage_key, agent_id, logical_path),
                )
                old_blob = object_root(request, agent_id) / old["storage_key"]
                old_blob.unlink(missing_ok=True)
        changed_paths.append(logical_path)
    return changed_paths


@router.post("/v1/agents/{agent_id}/workspace/commands", response_model=WorkspaceCommandResponse)
def run_workspace_command(agent_id: str, payload: WorkspaceCommandRequest, request: Request) -> WorkspaceCommandResponse:
    root = execution_root(request, agent_id)
    _materialize_workspace(agent_id, request, root)
    try:
        result = subprocess.run(
            payload.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=payload.timeout_seconds,
            cwd=root,
            env={**os.environ, **payload.env},
        )
    except subprocess.TimeoutExpired:
        raise_error("command_timeout", f"command timed out after {payload.timeout_seconds}s")
    changed_paths = _sync_workspace(agent_id, request, root)
    return WorkspaceCommandResponse(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        changed_paths=changed_paths,
    )
```

- [x] **Step 5: Run command API tests**

Run from `Agent-Home/`:

```bash
python3 -m pytest tests/test_workspace_command.py tests/test_workspace.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_home/config.py agent_home/errors.py agent_home/models.py agent_home/workspace.py tests/test_workspace_command.py
git commit -m "feat: add workspace command execution api"
```

## Task 2: Agent-Home Timeline Compatibility API

**Status:** Implemented in `Agent-Home/.worktrees/agent-home-integration`; spec review approved; code quality review approved; commit pending.

**Files:**
- Modify: `Agent-Home/agent_home/models.py`
- Modify: `Agent-Home/agent_home/timeline.py`
- Test: `Agent-Home/tests/test_timeline_compat.py`

- [x] **Step 1: Write failing compatibility endpoint tests**

Create `Agent-Home/tests/test_timeline_compat.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from agent_home.app import create_app
from agent_home.config import Settings


def make_client(tmp_path: Path):
    client = TestClient(create_app(Settings(database_path=tmp_path / "state.sqlite", object_root=tmp_path / "objects")))
    token = client.post("/v1/agents", json={"agent_id": "agent-a"}).json()["token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_list_and_patch_sessions(tmp_path: Path):
    client, headers = make_client(tmp_path)
    session = client.post("/v1/agents/agent-a/sessions", headers=headers, json={"session_id": "s1", "title": "old"}).json()

    listed = client.get("/v1/agents/agent-a/sessions", headers=headers)
    patched = client.patch("/v1/agents/agent-a/sessions/s1", headers=headers, json={"title": "new", "metadata": {"k": "v"}, "active_branch_id": session["active_branch_id"]})

    assert listed.status_code == 200
    assert listed.json()[0]["session_id"] == "s1"
    assert patched.status_code == 200
    assert patched.json()["title"] == "new"
    assert patched.json()["metadata"] == {"k": "v"}


def test_branch_create_and_get(tmp_path: Path):
    client, headers = make_client(tmp_path)
    session = client.post("/v1/agents/agent-a/sessions", headers=headers, json={"session_id": "s1"}).json()

    created = client.post("/v1/agents/agent-a/sessions/s1/branches", headers=headers, json={"branch_id": "b-custom", "parent_branch_id": session["active_branch_id"], "fork_checkpoint_id": "", "base_message_cursor": 0})
    loaded = client.get("/v1/agents/agent-a/branches/b-custom", headers=headers)

    assert created.status_code == 200
    assert created.json()["branch_id"] == "b-custom"
    assert loaded.status_code == 200
    assert loaded.json()["parent_branch_id"] == session["active_branch_id"]


def test_get_run_latest_run_and_checkpoint(tmp_path: Path):
    client, headers = make_client(tmp_path)
    session = client.post("/v1/agents/agent-a/sessions", headers=headers, json={"session_id": "s1"}).json()
    branch_id = session["active_branch_id"]
    client.post("/v1/agents/agent-a/runs", headers=headers, json={"run_id": "r1", "session_id": "s1", "branch_id": branch_id})
    client.post("/v1/agents/agent-a/messages", headers=headers, json={"message_id": "m1", "session_id": "s1", "branch_id": branch_id, "run_id": "r1", "role": "user", "content": "hello"})
    client.post("/v1/agents/agent-a/checkpoints", headers=headers, json={"checkpoint_id": "c1", "session_id": "s1", "branch_id": branch_id, "run_id": "r1", "kind": "user_snapshot", "name": "user_message_committed", "message_cursor": 0})

    run = client.get("/v1/agents/agent-a/runs/r1", headers=headers)
    latest = client.get(f"/v1/agents/agent-a/branches/{branch_id}/runs/latest", headers=headers)
    checkpoint = client.get("/v1/agents/agent-a/checkpoints/c1", headers=headers)

    assert run.status_code == 200
    assert run.json()["run_id"] == "r1"
    assert latest.status_code == 200
    assert latest.json()["run_id"] == "r1"
    assert checkpoint.status_code == 200
    assert checkpoint.json()["checkpoint_id"] == "c1"
```

- [x] **Step 2: Run test to verify it fails**

Run from `Agent-Home/`:

```bash
python3 -m pytest tests/test_timeline_compat.py -v
```

Expected: FAIL because list/patch session, branch create/get, get run/latest run, and get checkpoint endpoints are missing.

- [x] **Step 3: Add missing request models**

Append to `Agent-Home/agent_home/models.py`:

```python
class UpdateSessionRequest(BaseModel):
    title: str | None = None
    metadata: dict[str, Any] | None = None
    active_branch_id: str | None = None


class CreateBranchRequest(BaseModel):
    branch_id: str | None = None
    parent_branch_id: str = ""
    fork_checkpoint_id: str = ""
    base_message_cursor: int = 0
```

- [x] **Step 4: Implement compatibility endpoints**

Modify imports in `Agent-Home/agent_home/timeline.py`:

```python
from agent_home.models import (
    BranchResponse,
    CheckpointKind,
    CheckpointResponse,
    CreateBranchRequest,
    CreateCheckpointRequest,
    CreateMessageRequest,
    CreateRunRequest,
    CreateSessionRequest,
    MessageResponse,
    ResumeResponse,
    RewindRequest,
    RewindResponse,
    RunResponse,
    RunStatus,
    SessionResponse,
    UpdateBranchRequest,
    UpdateRunStatusRequest,
    UpdateSessionRequest,
)
```

Append these routes to `Agent-Home/agent_home/timeline.py`:

```python
@router.get("/v1/agents/{agent_id}/sessions", response_model=list[SessionResponse])
def list_sessions(agent_id: str, http_request: Request) -> list[SessionResponse]:
    rows = storage(http_request)._conn.execute(
        """
        SELECT session_id, agent_id, title, metadata, active_branch_id
        FROM sessions
        WHERE agent_id = ?
        ORDER BY updated_at DESC
        """,
        (agent_id,),
    ).fetchall()
    return [session_response(row) for row in rows]


@router.patch("/v1/agents/{agent_id}/sessions/{session_id}", response_model=SessionResponse)
def update_session(agent_id: str, session_id: str, request: UpdateSessionRequest, http_request: Request) -> SessionResponse:
    with storage(http_request).transaction() as connection:
        session = require_session(connection, agent_id, session_id)
        active_branch_id = request.active_branch_id if request.active_branch_id is not None else session["active_branch_id"]
        if active_branch_id:
            branch = require_branch(connection, agent_id, active_branch_id)
            if branch["session_id"] != session_id:
                raise_error("branch_not_found", f"branch {active_branch_id} not found for session {session_id}")
        title = request.title if request.title is not None else session["title"]
        metadata = request.metadata if request.metadata is not None else json.loads(session["metadata"])
        connection.execute(
            """
            UPDATE sessions
            SET title = ?, metadata = ?, active_branch_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE agent_id = ? AND session_id = ?
            """,
            (title, json.dumps(metadata), active_branch_id, agent_id, session_id),
        )
    return session_response(require_session(storage(http_request)._conn, agent_id, session_id))


@router.post("/v1/agents/{agent_id}/sessions/{session_id}/branches", response_model=BranchResponse)
def create_branch(agent_id: str, session_id: str, request: CreateBranchRequest, http_request: Request) -> BranchResponse:
    branch_id = request.branch_id or str(uuid4())
    with storage(http_request).transaction() as connection:
        require_session(connection, agent_id, session_id)
        if request.parent_branch_id:
            parent = require_branch(connection, agent_id, request.parent_branch_id)
            if parent["session_id"] != session_id:
                raise_error("branch_not_found", f"branch {request.parent_branch_id} not found for session {session_id}")
        connection.execute(
            """
            INSERT INTO branches(branch_id, session_id, agent_id, parent_branch_id, fork_checkpoint_id, base_message_cursor, resume_head)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (branch_id, session_id, agent_id, request.parent_branch_id, request.fork_checkpoint_id, request.base_message_cursor, ""),
        )
    return branch_response(require_branch(storage(http_request)._conn, agent_id, branch_id))


@router.get("/v1/agents/{agent_id}/branches/{branch_id}", response_model=BranchResponse)
def get_branch(agent_id: str, branch_id: str, http_request: Request) -> BranchResponse:
    return branch_response(require_branch(storage(http_request)._conn, agent_id, branch_id))


@router.get("/v1/agents/{agent_id}/runs/{run_id}", response_model=RunResponse)
def get_run(agent_id: str, run_id: str, http_request: Request) -> RunResponse:
    return run_response(require_run(storage(http_request)._conn, agent_id, run_id))


@router.get("/v1/agents/{agent_id}/branches/{branch_id}/runs/latest", response_model=RunResponse)
def get_latest_run(agent_id: str, branch_id: str, http_request: Request) -> RunResponse:
    require_branch(storage(http_request)._conn, agent_id, branch_id)
    row = storage(http_request)._conn.execute(
        """
        SELECT run_id, agent_id, session_id, branch_id, status
        FROM runs
        WHERE agent_id = ? AND branch_id = ?
        ORDER BY rowid DESC
        LIMIT 1
        """,
        (agent_id, branch_id),
    ).fetchone()
    if row is None:
        raise_error("run_not_found", f"no run found for branch {branch_id}")
    return run_response(row)


@router.get("/v1/agents/{agent_id}/checkpoints/{checkpoint_id}", response_model=CheckpointResponse)
def get_checkpoint(agent_id: str, checkpoint_id: str, http_request: Request) -> CheckpointResponse:
    return checkpoint_response(require_checkpoint(storage(http_request)._conn, agent_id, checkpoint_id))
```

- [x] **Step 5: Run compatibility tests**

Run from `Agent-Home/`:

```bash
python3 -m pytest tests/test_timeline_compat.py tests/test_timeline.py tests/test_resume_rewind.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_home/models.py agent_home/timeline.py tests/test_timeline_compat.py
git commit -m "feat: add timeline compatibility endpoints"
```

## Task 3: L-Agent Agent-Home Settings and Auto Initialization

**Status:** Implemented in `L-Agent/.worktrees/agent-home-integration`; spec review approved; code quality review approved after Important fixes; commit pending.

**Files:**
- Modify: `L-Agent/agent/config/settings.py`
- Create: `L-Agent/agent/home/__init__.py`
- Create: `L-Agent/agent/home/client.py`
- Test: `L-Agent/tests/test_agent_home_client.py`

- [x] **Step 1: Write failing settings and initialization tests**

Create `L-Agent/tests/test_agent_home_client.py`:

```python
from pathlib import Path

import httpx
import pytest

from agent.config.settings import AgentHomeSettings, Settings, write_agent_home_credentials
from agent.home.client import AgentHomeClient, AgentHomeError, initialize_agent_home


class FakeTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/v1/agents":
            return httpx.Response(201, json={"agent_id": "l-agent:test", "token": "tok", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
        if request.method == "GET" and request.url.path == "/v1/agents/l-agent:test":
            auth = request.headers.get("Authorization")
            if auth == "Bearer tok":
                return httpx.Response(200, json={"agent_id": "l-agent:test", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
            return httpx.Response(401, json={"error": {"code": "auth_failed", "message": "bad", "details": {}}})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "missing", "details": {}}})


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
```

- [x] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_client.py -v
```

Expected: FAIL with missing `AgentHomeSettings` and `agent.home.client`.

- [x] **Step 3: Implement settings support**

Modify `L-Agent/agent/config/settings.py`:

```python
"""Application settings loaded from YAML config file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib

import yaml


@dataclass
class LLMSettings:
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class ContextSettings:
    max_context_tokens: int = 128_000
    compression_threshold: float = 0.5
    protected_head: int = 3
    protected_tail_tokens: int = 20_000
    min_saving: float = 0.1


@dataclass
class BudgetSettings:
    max_iterations: int = 25
    max_tokens: int = 200_000


@dataclass
class AgentSettings:
    guidance_file: str = ""


@dataclass
class AgentHomeSettings:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8765"
    agent_id: str = ""
    token: str = ""
    auto_create_agent: bool = True
    auto_extract_memory: bool = False
    memory_prefetch_limit: int = 5


@dataclass
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    agent_home: AgentHomeSettings = field(default_factory=AgentHomeSettings)
    config_dir: Path = field(default_factory=lambda: Path("."))

    def resolve_file(self, relative_path: str) -> str:
        if not relative_path:
            return ""
        p = self.config_dir / relative_path
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8").strip()


DEFAULT_CONFIG_PATHS = [
    Path("workspace/config.yaml"),
    Path.home() / ".l-agent" / "config.yaml",
]


def default_agent_id(project_root: Path | None = None) -> str:
    root = (project_root or Path.cwd()).resolve()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return f"l-agent:{digest}"


def load_settings(config_path: Path | None = None) -> Settings:
    path = _resolve_path(config_path)
    if path is None:
        settings = Settings()
        settings.agent_home.agent_id = default_agent_id(Path.cwd())
        return settings

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    settings = _parse(data)
    settings.config_dir = path.parent
    if not settings.agent_home.agent_id:
        settings.agent_home.agent_id = default_agent_id(path.parent)
    return settings


def _resolve_path(config_path: Path | None) -> Path | None:
    if config_path and config_path.exists():
        return config_path
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _parse(data: dict[str, Any]) -> Settings:
    llm_data = data.get("llm", {})
    budget_data = data.get("budget", {})
    context_data = data.get("context", {})
    agent_data = data.get("agent", {})
    home_data = data.get("agent_home", {})

    return Settings(
        llm=LLMSettings(**{k: v for k, v in llm_data.items() if k in LLMSettings.__dataclass_fields__}),
        budget=BudgetSettings(**{k: v for k, v in budget_data.items() if k in BudgetSettings.__dataclass_fields__}),
        context=ContextSettings(**{k: v for k, v in context_data.items() if k in ContextSettings.__dataclass_fields__}),
        agent=AgentSettings(**{k: v for k, v in agent_data.items() if k in AgentSettings.__dataclass_fields__}),
        agent_home=AgentHomeSettings(**{k: v for k, v in home_data.items() if k in AgentHomeSettings.__dataclass_fields__}),
    )


def write_agent_home_credentials(config_path: Path, agent_id: str, token: str) -> None:
    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    data.setdefault("agent_home", {})
    data["agent_home"]["agent_id"] = agent_id
    data["agent_home"]["token"] = token
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
```

- [x] **Step 4: Implement AgentHomeClient base initialization**

Create `L-Agent/agent/home/__init__.py`:

```python
from agent.home.client import AgentHomeClient, AgentHomeError, initialize_agent_home

__all__ = ["AgentHomeClient", "AgentHomeError", "initialize_agent_home"]
```

Create `L-Agent/agent/home/client.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings, write_agent_home_credentials


@dataclass
class AgentHomeError(Exception):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class AgentHomeClient:
    def __init__(self, base_url: str, agent_id: str, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.token = token
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=30.0)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

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


def initialize_agent_home(settings: Settings, config_path: Path | None, transport: httpx.BaseTransport | None = None) -> AgentHomeClient:
    home = settings.agent_home
    client = AgentHomeClient(home.base_url, home.agent_id, home.token, transport=transport)
    if home.token:
        client.verify_agent()
        return client
    if not home.auto_create_agent:
        raise AgentHomeError("agent_home_token_missing", "agent_home.token is required when auto_create_agent is false", {})
    token = client.create_agent()
    if config_path is None:
        raise AgentHomeError("agent_home_config_missing", "cannot persist Agent-Home token without a config path", {})
    write_agent_home_credentials(config_path, home.agent_id, token)
    return client
```

- [x] **Step 5: Run initialization tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/config/settings.py agent/home tests/test_agent_home_client.py
git commit -m "feat: add agent home client initialization"
```

## Task 4: AgentHomeClient Timeline Adapter

**Files:**
- Modify: `L-Agent/agent/home/client.py`
- Test: `L-Agent/tests/test_agent_home_client.py`

- [ ] **Step 1: Add failing timeline adapter tests**

Append to `L-Agent/tests/test_agent_home_client.py`:

```python
from agent.timeline.models import AgentRun, Checkpoint, CheckpointKind, Message, RunStatus, Session


def make_timeline_client() -> AgentHomeClient:
    transport = FakeTransport()
    client = AgentHomeClient(base_url="http://test", agent_id="l-agent:test", token="tok", transport=transport)
    return client


def test_timeline_session_and_messages_round_trip_methods():
    client = make_timeline_client()
    session = Session(session_id="s1", title="demo")

    client.create_session(session)
    loaded = client.get_session("s1")
    branch_id = loaded.active_branch_id
    client.create_run(AgentRun(run_id="r1", session_id="s1", branch_id=branch_id))
    client.append_message(Message(message_id="m1", session_id="s1", branch_id=branch_id, run_id="r1", sequence=0, role="user", content="hello"))
    client.create_checkpoint(Checkpoint(checkpoint_id="c1", session_id="s1", branch_id=branch_id, run_id="r1", kind=CheckpointKind.user_snapshot, name="user_message_committed", message_cursor=0))

    assert loaded.session_id == "s1"
    assert client.get_latest_sequence(branch_id) == 0
    assert client.get_messages_by_branch(branch_id)[0].content == "hello"
    assert client.get_checkpoints_by_branch(branch_id)[0].checkpoint_id == "c1"


def test_update_run_status_and_resume_head():
    client = make_timeline_client()
    session = Session(session_id="s2")
    client.create_session(session)
    branch_id = client.get_session("s2").active_branch_id
    client.create_run(AgentRun(run_id="r2", session_id="s2", branch_id=branch_id))
    client.update_run_status("r2", RunStatus.completed)

    run = client.get_latest_run_by_branch(branch_id)

    assert run is not None
    assert run.status == RunStatus.completed
```

Modify `FakeTransport.handle_request` in `L-Agent/tests/test_agent_home_client.py` so it delegates unknown timeline routes to an in-memory ASGI app:

```python
# Replace FakeTransport with MockTransport from httpx in this file for timeline tests:
# use httpx.MockTransport and explicit route handlers, or run this test against Agent-Home later.
```

Use the following concrete replacement instead of the original `FakeTransport`:

```python
class FakeTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.sessions: dict[str, dict] = {}
        self.branches: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.checkpoints: dict[str, list[dict]] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/v1/agents":
            return httpx.Response(201, json={"agent_id": "l-agent:test", "token": "tok", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
        if request.method == "GET" and path == "/v1/agents/l-agent:test":
            if request.headers.get("Authorization") == "Bearer tok":
                return httpx.Response(200, json={"agent_id": "l-agent:test", "config": {"memory": {"auto_extract": {"enabled": False}}, "workspace": {}}})
            return httpx.Response(401, json={"error": {"code": "auth_failed", "message": "bad", "details": {}}})
        if request.method == "POST" and path == "/v1/agents/l-agent:test/sessions":
            body = json_loads(request)
            branch_id = f"b-{body['session_id']}"
            self.sessions[body["session_id"]] = {"session_id": body["session_id"], "agent_id": "l-agent:test", "title": body.get("title", ""), "metadata": body.get("metadata", {}), "active_branch_id": branch_id}
            self.branches[branch_id] = {"branch_id": branch_id, "session_id": body["session_id"], "parent_branch_id": "", "fork_checkpoint_id": "", "base_message_cursor": 0, "resume_head": ""}
            return httpx.Response(200, json=self.sessions[body["session_id"]])
        if request.method == "GET" and path.startswith("/v1/agents/l-agent:test/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=self.sessions[session_id])
        if request.method == "POST" and path == "/v1/agents/l-agent:test/runs":
            body = json_loads(request)
            run = {"run_id": body["run_id"], "agent_id": "l-agent:test", "session_id": body["session_id"], "branch_id": body["branch_id"], "status": "running"}
            self.runs[run["run_id"]] = run
            return httpx.Response(200, json=run)
        if request.method == "PATCH" and path.startswith("/v1/agents/l-agent:test/runs/"):
            run_id = path.split("/")[-2]
            self.runs[run_id]["status"] = json_loads(request)["status"]
            return httpx.Response(200, json=self.runs[run_id])
        if request.method == "POST" and path == "/v1/agents/l-agent:test/messages":
            body = json_loads(request)
            branch_id = body["branch_id"]
            sequence = len(self.messages.setdefault(branch_id, []))
            message = {**body, "agent_id": "l-agent:test", "sequence": sequence}
            self.messages[branch_id].append(message)
            return httpx.Response(200, json=message)
        if request.method == "GET" and path.endswith("/messages/latest-sequence"):
            branch_id = path.split("/")[-3]
            return httpx.Response(200, json={"sequence": len(self.messages.get(branch_id, [])) - 1})
        if request.method == "GET" and path.endswith("/messages"):
            branch_id = path.split("/")[-2]
            return httpx.Response(200, json=self.messages.get(branch_id, []))
        if request.method == "POST" and path == "/v1/agents/l-agent:test/checkpoints":
            body = json_loads(request)
            checkpoint = {**body, "agent_id": "l-agent:test", "metadata": body.get("metadata", {})}
            self.checkpoints.setdefault(body["branch_id"], []).append(checkpoint)
            return httpx.Response(200, json=checkpoint)
        if request.method == "GET" and path.endswith("/checkpoints"):
            branch_id = path.split("/")[-2]
            return httpx.Response(200, json=self.checkpoints.get(branch_id, []))
        if request.method == "GET" and path.endswith("/runs/latest"):
            branch_id = path.split("/")[-3]
            for run in reversed(list(self.runs.values())):
                if run["branch_id"] == branch_id:
                    return httpx.Response(200, json=run)
            return httpx.Response(404, json={"error": {"code": "run_not_found", "message": "missing", "details": {}}})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path, "details": {}}})


def json_loads(request: httpx.Request) -> dict:
    import json
    return json.loads(request.content.decode("utf-8"))
```

- [ ] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_client.py -v
```

Expected: FAIL because `AgentHomeClient` has no timeline methods.

- [ ] **Step 3: Implement timeline adapter methods**

Append to `L-Agent/agent/home/client.py` inside `AgentHomeClient`:

```python
    def create_session(self, session: Session) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/sessions", json={"session_id": session.session_id, "title": session.title, "metadata": session.metadata})

    def get_session(self, session_id: str) -> Session | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/sessions/{session_id}").json()
        except AgentHomeError as exc:
            if exc.code == "session_not_found":
                return None
            raise
        return Session(session_id=body["session_id"], title=body.get("title", ""), active_branch_id=body["active_branch_id"], metadata=body.get("metadata", {}))

    def update_session(self, session: Session) -> None:
        self._request("PATCH", f"/v1/agents/{self.agent_id}/sessions/{session.session_id}", json={"title": session.title, "metadata": session.metadata, "active_branch_id": session.active_branch_id})

    def list_sessions(self) -> list[Session]:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/sessions").json()
        return [Session(session_id=item["session_id"], title=item.get("title", ""), active_branch_id=item["active_branch_id"], metadata=item.get("metadata", {})) for item in body]

    def create_branch(self, branch: Branch) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/sessions/{branch.session_id}/branches", json={"branch_id": branch.branch_id, "parent_branch_id": branch.parent_branch_id, "fork_checkpoint_id": branch.fork_checkpoint_id, "base_message_cursor": branch.base_message_cursor})

    def get_branch(self, branch_id: str) -> Branch | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}").json()
        except AgentHomeError as exc:
            if exc.code == "branch_not_found":
                return None
            raise
        return Branch(branch_id=body["branch_id"], session_id=body["session_id"], parent_branch_id=body.get("parent_branch_id", ""), fork_checkpoint_id=body.get("fork_checkpoint_id", ""), base_message_cursor=body.get("base_message_cursor", 0), resume_head=body.get("resume_head", ""))

    def update_branch(self, branch: Branch) -> None:
        self._request("PATCH", f"/v1/agents/{self.agent_id}/branches/{branch.branch_id}", json={"resume_head": branch.resume_head})

    def create_run(self, run: AgentRun) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/runs", json={"run_id": run.run_id, "session_id": run.session_id, "branch_id": run.branch_id})

    def get_run(self, run_id: str) -> AgentRun | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/runs/{run_id}").json()
        except AgentHomeError as exc:
            if exc.code == "run_not_found":
                return None
            raise
        return AgentRun(run_id=body["run_id"], session_id=body["session_id"], branch_id=body["branch_id"], status=RunStatus(body["status"]))

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        self._request("PATCH", f"/v1/agents/{self.agent_id}/runs/{run_id}/status", json={"status": status.value})

    def get_latest_run_by_branch(self, branch_id: str) -> AgentRun | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/runs/latest").json()
        except AgentHomeError as exc:
            if exc.code == "run_not_found":
                return None
            raise
        return AgentRun(run_id=body["run_id"], session_id=body["session_id"], branch_id=body["branch_id"], status=RunStatus(body["status"]))

    def append_message(self, message: Message) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/messages", json={"message_id": message.message_id, "session_id": message.session_id, "branch_id": message.branch_id, "run_id": message.run_id, "role": message.role, "content": message.content, "tool_call_id": message.tool_call_id, "tool_calls": message.tool_calls})

    def get_messages_by_branch(self, branch_id: str, start: int = 0, end: int | None = None) -> list[Message]:
        params: dict[str, int] = {"start": start}
        if end is not None:
            params["end"] = end
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/messages", params=params).json()
        return [Message(message_id=item["message_id"], session_id=item["session_id"], branch_id=item["branch_id"], run_id=item.get("run_id") or "", sequence=item["sequence"], role=item["role"], content=item.get("content", ""), tool_call_id=item.get("tool_call_id", ""), tool_calls=item.get("tool_calls", [])) for item in body]

    def get_latest_sequence(self, branch_id: str) -> int:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/messages/latest-sequence").json()
        return body["sequence"]

    def create_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._request("POST", f"/v1/agents/{self.agent_id}/checkpoints", json={"checkpoint_id": checkpoint.checkpoint_id, "session_id": checkpoint.session_id, "branch_id": checkpoint.branch_id, "run_id": checkpoint.run_id, "kind": checkpoint.kind.value, "name": checkpoint.name, "message_cursor": checkpoint.message_cursor})

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        try:
            body = self._request("GET", f"/v1/agents/{self.agent_id}/checkpoints/{checkpoint_id}").json()
        except AgentHomeError as exc:
            if exc.code == "checkpoint_not_found":
                return None
            raise
        return Checkpoint(checkpoint_id=body["checkpoint_id"], session_id=body["session_id"], branch_id=body["branch_id"], run_id=body.get("run_id") or "", kind=CheckpointKind(body["kind"]), name=body["name"], message_cursor=body["message_cursor"])

    def get_checkpoints_by_branch(self, branch_id: str) -> list[Checkpoint]:
        body = self._request("GET", f"/v1/agents/{self.agent_id}/branches/{branch_id}/checkpoints").json()
        return [Checkpoint(checkpoint_id=item["checkpoint_id"], session_id=item["session_id"], branch_id=item["branch_id"], run_id=item.get("run_id") or "", kind=CheckpointKind(item["kind"]), name=item["name"], message_cursor=item["message_cursor"]) for item in body]

    def get_latest_stable_checkpoint(self, branch_id: str) -> Checkpoint | None:
        checkpoints = [cp for cp in self.get_checkpoints_by_branch(branch_id) if cp.kind == CheckpointKind.user_snapshot]
        return checkpoints[-1] if checkpoints else None
```

Also add imports near the top of `L-Agent/agent/home/client.py`:

```python
from agent.timeline.models import AgentRun, Branch, Checkpoint, CheckpointKind, Message, RunStatus, Session
```

- [ ] **Step 4: Run timeline adapter tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/home/client.py tests/test_agent_home_client.py
git commit -m "feat: adapt agent home client to timeline store"
```

## Task 5: Run Finalization Step

**Files:**
- Create: `L-Agent/agent/steps/after_agent.py`
- Modify: `L-Agent/agent/core/factory.py`
- Test: `L-Agent/tests/test_agent_home_memory.py`

- [ ] **Step 1: Write failing run finalization tests**

Create `L-Agent/tests/test_agent_home_memory.py`:

```python
from agent.core.context import RunContext
from agent.steps.after_agent import AgentHomeRunFinalize
from agent.timeline.models import Branch, Checkpoint, CheckpointKind, RunStatus


class FakeHome:
    def __init__(self):
        self.status_updates = []
        self.branch_updates = []
        self.extractions = []
        self.checkpoints = [Checkpoint("c-runtime", "s1", "b1", "r1", CheckpointKind.runtime, "model_call_completed", 0)]

    def update_run_status(self, run_id, status):
        self.status_updates.append((run_id, status))

    def get_checkpoints_by_branch(self, branch_id):
        return self.checkpoints

    def get_branch(self, branch_id):
        return Branch(branch_id=branch_id, session_id="s1")

    def update_branch(self, branch):
        self.branch_updates.append(branch)

    def extract_memory(self, session_id, trigger):
        self.extractions.append((session_id, trigger))


def test_completed_run_updates_status_and_resume_head():
    home = FakeHome()
    ctx = RunContext(session_id="s1", branch_id="b1", run_id="r1", status="completed", timeline_store=home)

    AgentHomeRunFinalize(auto_extract_memory=False).run(ctx)

    assert home.status_updates == [("r1", RunStatus.completed)]
    assert home.branch_updates[0].resume_head == "c-runtime"


def test_failed_run_does_not_update_resume_head():
    home = FakeHome()
    ctx = RunContext(session_id="s1", branch_id="b1", run_id="r1", status="failed", timeline_store=home)

    AgentHomeRunFinalize(auto_extract_memory=False).run(ctx)

    assert home.status_updates == [("r1", RunStatus.failed)]
    assert home.branch_updates == []


def test_auto_extract_only_when_enabled():
    home = FakeHome()
    ctx = RunContext(session_id="s1", branch_id="b1", run_id="r1", status="completed", timeline_store=home)

    AgentHomeRunFinalize(auto_extract_memory=True).run(ctx)

    assert home.extractions == [("s1", "after_agent")]
```

- [ ] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_memory.py -v
```

Expected: FAIL because `AgentHomeRunFinalize` does not exist.

- [ ] **Step 3: Implement run finalization step**

Create `L-Agent/agent/steps/after_agent.py`:

```python
from __future__ import annotations

from agent.core.context import RunContext
from agent.core.lifecycle import HookPhase
from agent.steps.base import Step
from agent.timeline.models import RunStatus


class AgentHomeRunFinalize(Step):
    def __init__(self, auto_extract_memory: bool = False) -> None:
        super().__init__("agent_home.run_finalize", HookPhase.after_agent)
        self._auto_extract_memory = auto_extract_memory

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None or not ctx.run_id:
            return
        status = RunStatus(ctx.status)
        store.update_run_status(ctx.run_id, status)
        if status == RunStatus.completed:
            self._update_resume_head(ctx)
            if self._auto_extract_memory and ctx.session_id:
                self._extract_memory(store, ctx.session_id)

    def _update_resume_head(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        checkpoints = store.get_checkpoints_by_branch(ctx.branch_id)
        runtime_checkpoints = [cp for cp in checkpoints if cp.run_id == ctx.run_id]
        if not runtime_checkpoints:
            return
        branch = store.get_branch(ctx.branch_id)
        if branch is None:
            return
        branch.resume_head = runtime_checkpoints[-1].checkpoint_id
        store.update_branch(branch)

    def _extract_memory(self, store, session_id: str) -> None:
        try:
            store.extract_memory(session_id, "after_agent")
        except Exception as exc:
            if getattr(exc, "code", "") == "auto_extract_disabled":
                return
            raise
```

Modify `L-Agent/agent/core/factory.py` imports:

```python
from agent.steps.after_agent import AgentHomeRunFinalize
```

Modify `build_runner` signature and registration:

```python
def build_runner(config_path: Path | None = None, home_client=None) -> AgentRunner:
    settings = load_settings(config_path)
    ...
    reg.register(AgentHomeRunFinalize(auto_extract_memory=settings.agent_home.auto_extract_memory))
```

- [ ] **Step 4: Run finalization tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_memory.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/steps/after_agent.py agent/core/factory.py tests/test_agent_home_memory.py
git commit -m "feat: finalize agent home runs"
```

## Task 6: Workspace File Tools and Terminal Tool

**Files:**
- Modify: `L-Agent/agent/home/client.py`
- Modify: `L-Agent/agent/tools/builtin/file_ops.py`
- Modify: `L-Agent/agent/tools/builtin/terminal.py`
- Modify: `L-Agent/agent/tools/builtin/__init__.py`
- Test: `L-Agent/tests/test_agent_home_tools.py`

- [ ] **Step 1: Write failing tool tests**

Create `L-Agent/tests/test_agent_home_tools.py`:

```python
from agent.tools.builtin import create_builtin_registry
from agent.tools.builtin.file_ops import create_agent_home_file_tools
from agent.tools.builtin.terminal import create_agent_home_terminal_tool


class FakeHome:
    def __init__(self):
        self.files = {}
        self.commands = []

    def workspace_put(self, path, content):
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        return {"path": path, "size": len(self.files[path])}

    def workspace_get_text(self, path):
        return self.files[path].decode("utf-8")

    def workspace_list(self, prefix):
        return [{"path": path, "kind": "file", "size": len(body)} for path, body in sorted(self.files.items()) if path.startswith(prefix)]

    def workspace_run_command(self, command, timeout_seconds=120, env=None):
        self.commands.append((command, timeout_seconds, env or {}))
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "changed_paths": ["/notes/todo.md"]}


def test_agent_home_file_tools_read_write_list_search():
    home = FakeHome()
    tools = {tool.name: tool for tool in create_agent_home_file_tools(home)}

    assert "Written 5 bytes to /notes/todo.md" == tools["write_file"].handler("/notes/todo.md", "hello")
    assert "1\thello" == tools["read_file"].handler("/notes/todo.md")
    assert "/notes/todo.md" in tools["list_directory"].handler("/notes")
    assert "/notes/todo.md:1: hello" in tools["search_file"].handler("hello", "/notes")


def test_agent_home_terminal_tool_uses_workspace_command_api():
    home = FakeHome()
    tool = create_agent_home_terminal_tool(home)

    result = tool.handler("printf ok", timeout=10)

    assert home.commands == [("printf ok", 10, {})]
    assert "ok" in result
    assert "[exit_code: 0]" in result
    assert "[changed_paths] /notes/todo.md" in result


def test_builtin_registry_with_home_does_not_register_local_tool_instances():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)

    assert registry.get("read_file") is not None
    assert registry.get("terminal") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_tools.py -v
```

Expected: FAIL because Agent-Home tool factories do not exist.

- [ ] **Step 3: Add workspace methods to AgentHomeClient**

Append to `L-Agent/agent/home/client.py` inside `AgentHomeClient`:

```python
    def workspace_put(self, path: str, content: str | bytes) -> dict[str, Any]:
        body = content.encode("utf-8") if isinstance(content, str) else content
        return self._request("PUT", f"/v1/agents/{self.agent_id}/workspace/object", params={"path": path}, content=body).json()

    def workspace_get_bytes(self, path: str) -> bytes:
        return self._request("GET", f"/v1/agents/{self.agent_id}/workspace/object", params={"path": path}).content

    def workspace_get_text(self, path: str) -> str:
        return self.workspace_get_bytes(path).decode("utf-8", errors="replace")

    def workspace_list(self, prefix: str = "/") -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/agents/{self.agent_id}/workspace/objects", params={"prefix": prefix}).json()

    def workspace_run_command(self, command: str, timeout_seconds: int = 120, env: dict[str, str] | None = None) -> dict[str, Any]:
        return self._request("POST", f"/v1/agents/{self.agent_id}/workspace/commands", json={"command": command, "timeout_seconds": timeout_seconds, "env": env or {}}).json()
```

- [ ] **Step 4: Implement Agent-Home file tools**

Append to `L-Agent/agent/tools/builtin/file_ops.py`:

```python

def _numbered_text(text: str, offset: int = 1, limit: int | None = None) -> str:
    lines = text.splitlines()
    start = max(0, offset - 1)
    end = start + limit if limit else len(lines)
    return "\n".join(f"{i}\t{line}" for i, line in enumerate(lines[start:end], start=start + 1))


def create_agent_home_file_tools(home_client):
    def read_file(file_path: str, offset: int = 1, limit: int | None = None) -> str:
        return _numbered_text(home_client.workspace_get_text(file_path), offset, limit)

    def write_file(file_path: str, content: str) -> str:
        home_client.workspace_put(file_path, content)
        return f"Written {len(content.encode('utf-8'))} bytes to {file_path}"

    def list_directory(path: str, recursive: bool = False, pattern: str | None = None) -> str:
        import fnmatch
        objects = home_client.workspace_list(path)
        entries = []
        for item in objects:
            logical_path = item["path"]
            if pattern and not fnmatch.fnmatch(logical_path.rsplit("/", 1)[-1], pattern):
                continue
            entries.append(logical_path)
        return "\n".join(entries) if entries else "(empty)"

    def search_file(pattern: str, path: str = "/", file_pattern: str | None = None) -> str:
        import fnmatch
        import re
        regex = re.compile(pattern)
        matches: list[str] = []
        for item in home_client.workspace_list(path):
            logical_path = item["path"]
            if file_pattern and not fnmatch.fnmatch(logical_path.rsplit("/", 1)[-1], file_pattern):
                continue
            for i, line in enumerate(home_client.workspace_get_text(logical_path).splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{logical_path}:{i}: {line}")
        return "\n".join(matches) if matches else "No matches found."

    return [
        ToolSpec(name="read_file", description="Read a file from the Agent-Home workspace logical path. Paths are logical workspace paths such as /notes/todo.md, not local filesystem paths.", parameters_schema=read_file_tool.parameters_schema, handler=read_file),
        ToolSpec(name="write_file", description="Write a file to the Agent-Home workspace logical path. Paths are logical workspace paths such as /notes/todo.md, not local filesystem paths.", parameters_schema=write_file_tool.parameters_schema, handler=write_file),
        ToolSpec(name="list_directory", description="List Agent-Home workspace logical paths under a prefix.", parameters_schema=list_directory_tool.parameters_schema, handler=list_directory),
        ToolSpec(name="search_file", description="Search file contents inside Agent-Home workspace logical paths.", parameters_schema=search_file_tool.parameters_schema, handler=search_file),
    ]
```

- [ ] **Step 5: Implement Agent-Home terminal tool**

Append to `L-Agent/agent/tools/builtin/terminal.py`:

```python

def create_agent_home_terminal_tool(home_client) -> ToolSpec:
    def handler(command: str, timeout: int = 120) -> str:
        result = home_client.workspace_run_command(command, timeout_seconds=timeout)
        parts: list[str] = []
        if result.get("stdout"):
            parts.append(result["stdout"])
        if result.get("stderr"):
            parts.append(f"[stderr]\n{result['stderr']}")
        changed_paths = result.get("changed_paths", [])
        if changed_paths:
            parts.append("[changed_paths] " + ", ".join(changed_paths))
        parts.append(f"[exit_code: {result['exit_code']}]")
        return "\n".join(parts)

    return ToolSpec(
        name="terminal",
        description="Execute a shell command inside the Agent-Home workspace sandbox. The command runs in the agent workspace, not the local project directory.",
        parameters_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute inside the Agent-Home workspace sandbox."},
                "timeout": {"type": "integer", "description": "Timeout in seconds. Default: 120."},
            },
            "required": ["command"],
        },
        handler=handler,
    )
```

- [ ] **Step 6: Update built-in registry**

Modify `L-Agent/agent/tools/builtin/__init__.py`:

```python
"""Built-in tools registry and approval configuration."""

from agent.tools.builtin.file_ops import (
    create_agent_home_file_tools,
    list_directory_tool,
    read_file_tool,
    search_file_tool,
    write_file_tool,
)
from agent.tools.builtin.terminal import create_agent_home_terminal_tool, terminal_tool
from agent.tools.builtin.think import think_tool
from agent.tools.builtin.web import web_fetch_tool, web_search_tool
from agent.tools.registry import ToolRegistry

LOCAL_FILE_TOOLS = [read_file_tool, write_file_tool, list_directory_tool, search_file_tool]

AUTO_APPROVE_TOOLS = frozenset({
    "think",
    "read_file",
    "list_directory",
    "search_file",
    "web_search",
    "web_fetch",
})

ALWAYS_CONFIRM_TOOLS = frozenset({
    "terminal",
    "write_file",
})


def create_builtin_registry(home_client=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(think_tool)
    if home_client is None:
        for tool in LOCAL_FILE_TOOLS:
            registry.register(tool)
        registry.register(terminal_tool)
    else:
        for tool in create_agent_home_file_tools(home_client):
            registry.register(tool)
        registry.register(create_agent_home_terminal_tool(home_client))
    registry.register(web_search_tool)
    registry.register(web_fetch_tool)
    return registry
```

- [ ] **Step 7: Run tool tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_tools.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add agent/home/client.py agent/tools/builtin/file_ops.py agent/tools/builtin/terminal.py agent/tools/builtin/__init__.py tests/test_agent_home_tools.py
git commit -m "feat: route builtin tools through agent home workspace"
```

## Task 7: Memory Search, Prefetch, and CLI Commands

**Status:** Implemented in `L-Agent/.worktrees/agent-home-integration`; expanded coverage for review feedback; spec review approved; code quality review approved; commit pending.

**Files:**
- Modify: `L-Agent/agent/home/client.py`
- Modify: `L-Agent/agent/core/context.py`
- Modify: `L-Agent/agent/steps/before_agent.py`
- Modify: `L-Agent/agent/cli/commands.py`
- Test: `L-Agent/tests/test_agent_home_memory.py`

- [x] **Step 1: Add failing memory tests**

Append to `L-Agent/tests/test_agent_home_memory.py`:

```python
from agent.llm.types import BaseModelContext
from agent.steps.before_agent import MemoryPrefetch


class FakeMemoryHome(FakeHome):
    def __init__(self):
        super().__init__()
        self.memories = [{"type": "preference", "content": "Use python3", "tags": ["python"]}]

    def search_memory(self, q, type=None, tags=None):
        return self.memories if "python" in q.lower() else []

    def create_memory(self, type, content, tags=None, source_session_id="", source_message_ids=None, confidence=1.0):
        memory = {"type": type, "content": content, "tags": tags or []}
        self.memories.append(memory)
        return memory


def test_memory_prefetch_injects_matching_memories():
    home = FakeMemoryHome()
    ctx = RunContext(input="python command?", base_model_context=BaseModelContext(), home_client=home)

    MemoryPrefetch(limit=5).run(ctx)

    assert ctx.base_model_context.memory_context == "Memory:\n- [preference] Use python3"
```

- [x] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_memory.py -v
```

Expected: FAIL because `RunContext.home_client` and `MemoryPrefetch(limit=...)` do not exist.

- [x] **Step 3: Add home_client to RunContext**

Modify `L-Agent/agent/core/context.py`:

```python
    # --- Agent-Home ---
    home_client: Any = None
```

Place it after `timeline_store` so existing fields remain stable:

```python
    # --- timeline store ---
    timeline_store: TimelineStore | None = None

    # --- Agent-Home ---
    home_client: Any = None
```

- [x] **Step 4: Add memory methods to AgentHomeClient**

Append to `L-Agent/agent/home/client.py` inside `AgentHomeClient`:

```python
    def search_memory(self, q: str, type: str | None = None, tags: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"q": q}
        if type is not None:
            params["type"] = type
        if tags:
            params["tags"] = ",".join(tags)
        return self._request("GET", f"/v1/agents/{self.agent_id}/memory/search", params=params).json()

    def create_memory(self, type: str, content: str, tags: list[str] | None = None, source_session_id: str = "", source_message_ids: list[str] | None = None, confidence: float = 1.0) -> dict[str, Any]:
        return self._request("POST", f"/v1/agents/{self.agent_id}/memory", json={"type": type, "content": content, "tags": tags or [], "source_session_id": source_session_id, "source_message_ids": source_message_ids or [], "confidence": confidence}).json()

    def update_memory(self, memory_id: str, content: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        payload = {"content": content, "tags": tags}
        return self._request("PATCH", f"/v1/agents/{self.agent_id}/memory/{memory_id}", json={k: v for k, v in payload.items() if v is not None}).json()

    def delete_memory(self, memory_id: str) -> None:
        self._request("DELETE", f"/v1/agents/{self.agent_id}/memory/{memory_id}")

    def extract_memory(self, session_id: str, trigger: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/agents/{self.agent_id}/memory/extractions", json={"session_id": session_id, "trigger": trigger}).json()
```

- [x] **Step 5: Update MemoryPrefetch**

Modify `L-Agent/agent/steps/before_agent.py` `MemoryPrefetch` class:

```python
class MemoryPrefetch(Step):
    def __init__(self, limit: int = 5) -> None:
        super().__init__("memory.prefetch", HookPhase.before_agent)
        self._limit = limit

    def run(self, ctx: RunContext) -> None:
        if ctx.base_model_context is None:
            return
        home = ctx.home_client or ctx.timeline_store
        if home is None or not hasattr(home, "search_memory"):
            ctx.base_model_context.memory_context = None
            return
        memories = home.search_memory(ctx.input)[: self._limit]
        if not memories:
            ctx.base_model_context.memory_context = None
            return
        lines = ["Memory:"]
        for memory in memories:
            lines.append(f"- [{memory.get('type', 'note')}] {memory.get('content', '')}")
        ctx.base_model_context.memory_context = "\n".join(lines)
```

- [x] **Step 6: Update CLI memory commands**

Modify `L-Agent/agent/cli/commands.py`:

```python
# In handlers dict add:
"/memory": self._cmd_memory,
```

Append method to `CommandDispatcher`:

```python
    async def _cmd_memory(self, arg: str) -> None:
        parts = arg.strip().split(maxsplit=1)
        if not parts:
            self._console.print("[bold]Usage:[/bold] /memory add <content> | /memory search <query> | /memory extract")
            return
        action = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        if action == "add" and value:
            memory = self._store.create_memory("note", value, source_session_id=self._session_id)
            self._console.print(f"[green]Memory added:[/green] {memory.get('memory_id', '')}")
            return
        if action == "search" and value:
            memories = self._store.search_memory(value)
            for memory in memories:
                self._console.print(f"[{memory.get('type', 'note')}] {memory.get('content', '')}")
            if not memories:
                self._console.print("[dim]No memories found.[/dim]")
            return
        if action == "extract":
            try:
                self._store.extract_memory(self._session_id, "manual")
                self._console.print("[green]Memory extraction requested.[/green]")
            except Exception as exc:
                if getattr(exc, "code", "") == "auto_extract_disabled":
                    self._console.print("[yellow]Agent-Home auto extraction is disabled.[/yellow]")
                    return
                raise
            return
        self._console.print("[bold]Usage:[/bold] /memory add <content> | /memory search <query> | /memory extract")
```

- [x] **Step 7: Run memory tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_memory.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add agent/home/client.py agent/core/context.py agent/steps/before_agent.py agent/cli/commands.py tests/test_agent_home_memory.py
git commit -m "feat: connect memory to agent home"
```

## Task 8: CLI Main Path Migration

**Files:**
- Modify: `L-Agent/agent/core/factory.py`
- Modify: `L-Agent/agent/cli/app.py`
- Modify: `L-Agent/agent/cli/commands.py`
- Test: `L-Agent/tests/test_agent_home_cli.py`

- [ ] **Step 1: Write failing CLI integration tests**

Create `L-Agent/tests/test_agent_home_cli.py`:

```python
from rich.console import Console

from agent.cli.commands import CommandDispatcher
from agent.timeline.models import Session


class FakeHome:
    def __init__(self):
        self.sessions = []
        self.created = False

    def create_session(self, session):
        session.active_branch_id = "b1"
        self.sessions.append(session)
        self.created = True

    def list_sessions(self):
        return self.sessions

    def get_messages_by_branch(self, branch_id):
        return []

    def get_checkpoints_by_branch(self, branch_id):
        return []


def test_new_command_uses_agent_home_store():
    home = FakeHome()
    dispatcher = CommandDispatcher(home, Console(record=True))

    import asyncio
    asyncio.run(dispatcher.dispatch("/new"))

    assert home.created is True
    assert dispatcher.session_id
    assert dispatcher.branch_id == "b1"
```

- [ ] **Step 2: Run test to verify it fails**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_cli.py -v
```

Expected: PASS may already occur if `CommandDispatcher` accepts generic store; if FAIL due type imports, continue with implementation.

- [ ] **Step 3: Update factory to pass home client into tools and context**

Modify `L-Agent/agent/core/factory.py`:

```python
def build_runner(config_path: Path | None = None, home_client=None) -> AgentRunner:
    settings = load_settings(config_path)
    ...
    tool_registry = create_builtin_registry(home_client=home_client)
    ...
    reg.register(MemoryPrefetch(limit=settings.agent_home.memory_prefetch_limit))
    ...
    reg.register(AgentHomeRunFinalize(auto_extract_memory=settings.agent_home.auto_extract_memory))
```

- [ ] **Step 4: Update CLI app main path**

Modify `L-Agent/agent/cli/app.py` imports:

```python
from agent.config.settings import load_settings
from agent.home import initialize_agent_home
```

Remove import:

```python
from agent.storage.sqlite import SQLiteTimelineStore
```

Modify `CLISession.__init__` signature:

```python
    def __init__(self, runner: AgentRunner, store, config_path: Path | None = None) -> None:
```

Modify `_handle_run` context:

```python
        ctx = RunContext(
            input=user_input,
            session_id=self._session_id,
            branch_id=self._branch_id,
            timeline_store=self._store,
            home_client=self._store,
            auto_approve_tools=self._approval._auto_approve,
            always_confirm_tools=self._always_confirm,
        )
```

Modify `main()`:

```python
@app.command()
def main(
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Config YAML path"),
) -> None:
    config_path = Path(config) if config else None
    settings = load_settings(config_path)
    resolved_config_path = config_path or Path("workspace/config.yaml")
    home_client = initialize_agent_home(settings, config_path=resolved_config_path)
    runner = build_runner(config_path, home_client=home_client)
    cli_session = CLISession(runner, home_client, config_path)
    asyncio.run(cli_session.start(session_id=session))
```

Remove the `--db` option from CLI main.

- [ ] **Step 5: Run CLI tests**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_cli.py tests/test_agent_home_tools.py tests/test_agent_home_memory.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/core/factory.py agent/cli/app.py agent/cli/commands.py tests/test_agent_home_cli.py
git commit -m "feat: switch cli main path to agent home"
```

## Task 9: End-to-End Test Pass and Legacy Assertions

**Files:**
- Modify only if required: `L-Agent/tests/*.py`
- Modify only if required: `Agent-Home/tests/*.py`

- [ ] **Step 1: Run Agent-Home full suite**

Run from `Agent-Home/`:

```bash
python3 -m pytest -v
```

Expected: PASS. If FAIL on command timeout status, confirm `command_timeout` is mapped to HTTP 408 in `agent_home/errors.py`.

- [ ] **Step 2: Run L-Agent focused suite**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_client.py tests/test_agent_home_tools.py tests/test_agent_home_memory.py tests/test_agent_home_cli.py -v
```

Expected: PASS.

- [ ] **Step 3: Run L-Agent full suite**

Run from `L-Agent/`:

```bash
python3 -m pytest -v
```

Expected: PASS or expected legacy timeline tests fail because they directly assert SQLite-only behavior. If legacy tests fail due CLI main path no longer accepting `--db`, update those tests to construct stores directly instead of invoking CLI main with `--db`.

- [ ] **Step 4: Add no-local-main-path regression**

Append to `L-Agent/tests/test_agent_home_cli.py`:

```python
def test_cli_module_no_longer_imports_sqlite_timeline_store():
    import inspect
    import agent.cli.app as cli_app

    source = inspect.getsource(cli_app)

    assert "SQLiteTimelineStore" not in source
    assert "workspace/timeline.db" not in source
```

- [ ] **Step 5: Run regression test**

Run from `L-Agent/`:

```bash
python3 -m pytest tests/test_agent_home_cli.py::test_cli_module_no_longer_imports_sqlite_timeline_store -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent tests
git commit -m "test: verify agent home main path"
```

## Task 10: Manual Smoke Test

**Files:**
- No code changes unless smoke fails.

- [ ] **Step 1: Start Agent-Home daemon**

Run from `Agent-Home/`:

```bash
python3 -m agent_home.main
```

Expected: Uvicorn listens on `127.0.0.1:8765`.

- [ ] **Step 2: Run L-Agent CLI with a test config**

Create a temporary config file outside git-tracked paths, for example `/tmp/l-agent-agent-home-smoke.yaml`:

```yaml
llm:
  api_key: "dummy"
agent_home:
  enabled: true
  base_url: "http://127.0.0.1:8765"
  agent_id: "l-agent:smoke"
  token: ""
  auto_create_agent: true
  auto_extract_memory: false
```

Run from `L-Agent/`:

```bash
python3 -m agent.cli.app --config /tmp/l-agent-agent-home-smoke.yaml
```

Expected: CLI starts and writes `agent_home.token` into `/tmp/l-agent-agent-home-smoke.yaml`.

- [ ] **Step 3: Verify workspace tools through chat or direct unit entry**

In the CLI, ask the agent to write a logical workspace file. If model access is unavailable because the smoke config uses a dummy LLM key, skip interactive model call and rely on automated tests from Tasks 5-8.

Expected when model access is available: file operations use logical paths such as `/notes/todo.md`, not host project paths.

- [ ] **Step 4: Stop daemon**

Stop the Agent-Home process with Ctrl+C.

Expected: process exits cleanly.

## Self-Review Checklist

- Spec coverage:
  - Automatic `agent_id + token` initialization: Task 2.
  - No daemon lifecycle management by L-Agent: Task 7 and Task 9 keep Agent-Home startup external.
  - Timeline through AgentHomeClient: Task 2, Task 4, Task 5, Task 8.
  - Workspace logical file tools: Task 6.
  - Terminal in workspace sandbox: Task 1 and Task 6.
  - Memory search/prefetch/manual/extraction trigger: Task 5 and Task 7.
  - No SQLite CLI fallback: Task 8 and Task 9.
  - Structured error parsing: Task 3.
- Placeholder scan: no placeholder markers remain; each code-changing task includes concrete code.
- Type consistency:
  - `AgentHomeClient` method names match calls in tools, steps, and CLI.
  - `AgentHomeSettings` field names match YAML keys and factory references.
  - `WorkspaceCommandRequest.timeout_seconds` maps to L-Agent terminal `timeout`.
  - `RunContext.home_client` is optional and does not break existing tests.
