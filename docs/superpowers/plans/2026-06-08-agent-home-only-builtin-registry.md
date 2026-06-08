# 仅保留 Agent Home 内置工具注册 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除内置工具注册表的本地工具聚合路径，使 `create_builtin_registry` 只能注册 Agent Home-backed 工具，并在缺少 `home_client` 时抛出 `RuntimeError`。

**Architecture:** 保留底层本地工具 handler 的独立测试，但让 `agent/tools/builtin/__init__.py` 只作为 Agent Home 工具注册入口。注册表仍暴露相同工具名，文件/终端工具的实现全部来自 `home_client.workspace_*` 接口。

**Tech Stack:** Python 3.11+、pytest、现有 `ToolRegistry` / `ToolSpec` / `ToolDispatcher`。

---

## 文件结构与职责

- 修改：`agent/tools/builtin/__init__.py`
  - 删除本地工具聚合入口 `ALL_BUILTIN_TOOLS`。
  - 删除本地文件/终端工具对象的导入。
  - `create_builtin_registry` 在 `home_client is None` 时抛出 `RuntimeError`。
  - 只注册 Agent Home 文件工具、Agent Home 终端工具、`think`、`web_search`、`web_fetch`。

- 修改：`tests/test_agent_home_tools.py`
  - 增加 `create_builtin_registry(None)` 抛错测试。
  - 增加 Agent Home-only registry 工具名/schema 测试。
  - 增加通过 `ToolDispatcher` 调用 registry 中 `read_file` 的测试，验证会走 fake Agent Home client。
  - 增强 `FakeHome`，记录 workspace API 调用，便于断言工具没有走本地路径。

- 修改：`tests/test_builtin_tools.py`
  - 移除对 `ALL_BUILTIN_TOOLS` 和 `create_builtin_registry` 的导入。
  - 移除此前依赖无参 `create_builtin_registry()` 的 registry/dispatcher 集成测试。
  - 保留本地 handler 的底层单元测试，因为 spec 非目标明确不删除底层本地实现。

---

### Task 1: 增加 Agent Home-only registry 失败测试和集成测试

**Files:**
- Modify: `tests/test_agent_home_tools.py`
- Test: `tests/test_agent_home_tools.py`

- [ ] **Step 1: 更新测试文件导入**

将 `tests/test_agent_home_tools.py` 顶部导入改为：

```python
import pytest

from agent.tools.base import ToolCall, ToolPlan, ToolResultStatus
from agent.tools.builtin import create_builtin_registry
from agent.tools.builtin.file_ops import create_agent_home_file_tools
from agent.tools.builtin.terminal import create_agent_home_terminal_tool
from agent.tools.dispatcher import ToolDispatcher
```

- [ ] **Step 2: 增强 FakeHome 以记录 workspace API 调用**

将 `FakeHome` 类替换为下面完整实现：

```python
class FakeHome:
    def __init__(self):
        self.files = {}
        self.commands = []
        self.reads = []
        self.writes = []
        self.lists = []

    def workspace_put(self, path, content):
        self.writes.append((path, content))
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        return {"path": path, "size": len(self.files[path])}

    def workspace_get_text(self, path):
        self.reads.append(path)
        return self.files[path].decode("utf-8")

    def workspace_list(self, prefix):
        self.lists.append(prefix)
        return [
            {"path": path, "kind": "file", "size": len(body)}
            for path, body in sorted(self.files.items())
            if path.startswith(prefix)
        ]

    def workspace_run_command(self, command, timeout_seconds=120, env=None):
        self.commands.append((command, timeout_seconds, env or {}))
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "changed_paths": ["/notes/todo.md"]}
```

- [ ] **Step 3: 添加缺少 home_client 时抛 RuntimeError 的失败测试**

在 `tests/test_agent_home_tools.py` 末尾添加：

```python
def test_builtin_registry_requires_home_client():
    with pytest.raises(RuntimeError, match="Agent Home client is required"):
        create_builtin_registry(home_client=None)
```

- [ ] **Step 4: 添加 registry 只暴露预期工具名和 schema 的测试**

在 `tests/test_agent_home_tools.py` 末尾继续添加：

```python
def test_builtin_registry_with_home_exposes_expected_tools_and_schemas():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)

    expected_tool_names = {
        "think",
        "read_file",
        "write_file",
        "list_directory",
        "search_file",
        "terminal",
        "web_search",
        "web_fetch",
    }

    assert {schema["function"]["name"] for schema in registry.list_schemas()} == expected_tool_names
    for tool_name in expected_tool_names:
        assert registry.get(tool_name) is not None

    for schema in registry.list_schemas():
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert "required" in func["parameters"]
```

- [ ] **Step 5: 添加 dispatcher 经 registry 调用 Agent Home read_file 的测试**

在 `tests/test_agent_home_tools.py` 末尾继续添加：

```python
def test_dispatcher_read_file_uses_agent_home_workspace_client():
    home = FakeHome()
    home.workspace_put("/notes/test.txt", "content here\n")
    registry = create_builtin_registry(home_client=home)
    dispatcher = ToolDispatcher(registry)
    plan = ToolPlan(calls=[
        ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": "/notes/test.txt"}),
    ])

    results = dispatcher.dispatch(plan)

    assert results[0].status == ToolResultStatus.success
    assert "content here" in results[0].content
    assert home.reads == ["/notes/test.txt"]
```

- [ ] **Step 6: 运行新增测试，确认当前实现至少有一个失败**

Run:

```bash
pytest tests/test_agent_home_tools.py -v
```

Expected:

- `test_builtin_registry_requires_home_client` 失败，因为当前 `create_builtin_registry(home_client=None)` 不抛 `RuntimeError`。
- 其他新增 registry 测试可能通过或失败，取决于当前实现是否仍注册本地工具集合。

---

### Task 2: 移除无参 registry 旧测试依赖

**Files:**
- Modify: `tests/test_builtin_tools.py`
- Test: `tests/test_builtin_tools.py`

- [ ] **Step 1: 删除 registry/dispatcher 相关导入**

将 `tests/test_builtin_tools.py` 顶部导入从：

```python
from agent.tools.base import ToolCall, ToolPlan, ToolResultStatus
from agent.tools.builtin import (
    ALL_BUILTIN_TOOLS,
    AUTO_APPROVE_TOOLS,
    ALWAYS_CONFIRM_TOOLS,
    create_builtin_registry,
)
```

改为：

```python
from agent.tools.builtin import (
    AUTO_APPROVE_TOOLS,
    ALWAYS_CONFIRM_TOOLS,
)
```

并删除：

```python
from agent.tools.dispatcher import ToolDispatcher
```

- [ ] **Step 2: 删除依赖无参 create_builtin_registry 的测试类**

从 `tests/test_builtin_tools.py` 删除以下两个完整测试类：

```python
class TestBuiltinRegistry:
    def test_all_tools_registered(self):
        registry = create_builtin_registry()
        for tool in ALL_BUILTIN_TOOLS:
            assert registry.get(tool.name) is not None

    def test_schemas_complete(self):
        registry = create_builtin_registry()
        schemas = registry.list_schemas()
        assert len(schemas) == len(ALL_BUILTIN_TOOLS)
        for schema in schemas:
            func = schema["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert "required" in func["parameters"]
```

以及：

```python
class TestDispatcherIntegration:
    def test_read_file_via_dispatcher(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content here\n")
        registry = create_builtin_registry()
        dispatcher = ToolDispatcher(registry)
        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": str(f)}),
        ])
        results = dispatcher.dispatch(plan)
        assert results[0].status == ToolResultStatus.success
        assert "content here" in results[0].content

    def test_error_stays_internal(self):
        registry = create_builtin_registry()
        dispatcher = ToolDispatcher(registry)
        plan = ToolPlan(calls=[
            ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": "/no/such/file"}),
        ])
        results = dispatcher.dispatch(plan)
        assert results[0].status == ToolResultStatus.error
        assert "not found" in results[0].content.lower()
```

这些行为会由 `tests/test_agent_home_tools.py` 中的 Agent Home registry 测试覆盖。

- [ ] **Step 3: 运行本地 handler 测试，确认没有 import 错误**

Run:

```bash
pytest tests/test_builtin_tools.py -v
```

Expected:

- 当前实现阶段可能仍通过。
- 如果出现 `ImportError` 或 unused import 不会由 pytest 报错，但需要确保没有引用已删除导入的名称。

---

### Task 3: 修改 built-in registry 为 Agent Home-only

**Files:**
- Modify: `agent/tools/builtin/__init__.py`
- Test: `tests/test_agent_home_tools.py`

- [ ] **Step 1: 用 Agent Home-only 实现替换 `agent/tools/builtin/__init__.py` 内容**

将 `agent/tools/builtin/__init__.py` 改为下面完整内容：

```python
"""Built-in tools registry and approval configuration."""

from typing import Protocol

from agent.tools.builtin.file_ops import AgentHomeWorkspace, create_agent_home_file_tools
from agent.tools.builtin.terminal import AgentHomeCommandRunner, create_agent_home_terminal_tool
from agent.tools.builtin.think import think_tool
from agent.tools.builtin.web import web_fetch_tool, web_search_tool
from agent.tools.registry import ToolRegistry

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


class AgentHomeToolClient(AgentHomeWorkspace, AgentHomeCommandRunner, Protocol):
    pass


def create_builtin_registry(home_client: AgentHomeToolClient | None = None) -> ToolRegistry:
    if home_client is None:
        raise RuntimeError("Agent Home client is required to create the built-in tool registry.")

    registry = ToolRegistry()
    tools = [
        think_tool,
        *create_agent_home_file_tools(home_client),
        create_agent_home_terminal_tool(home_client),
        web_search_tool,
        web_fetch_tool,
    ]
    for tool in tools:
        registry.register(tool)
    return registry
```

- [ ] **Step 2: 运行 Agent Home registry 测试，确认通过**

Run:

```bash
pytest tests/test_agent_home_tools.py -v
```

Expected:

- 所有 `tests/test_agent_home_tools.py` 测试通过。
- `test_builtin_registry_requires_home_client` 通过，证明缺少 `home_client` 会抛出 `RuntimeError`。

- [ ] **Step 3: 检查 `ALL_BUILTIN_TOOLS` 是否仍被代码引用**

Run:

```bash
rg "ALL_BUILTIN_TOOLS" .
```

Expected:

- 不应有源码或测试引用。
- 如果历史文档中仍出现旧内容，不需要为本次功能修改历史文档，除非 pytest 或 import 受影响。

---

### Task 4: 运行聚焦回归测试并修复遗漏

**Files:**
- Modify if needed: `tests/test_agent_home_tools.py`
- Modify if needed: `tests/test_builtin_tools.py`
- Modify if needed: `agent/tools/builtin/__init__.py`

- [ ] **Step 1: 运行两个相关测试文件**

Run:

```bash
pytest tests/test_agent_home_tools.py tests/test_builtin_tools.py -v
```

Expected:

- 两个测试文件全部通过。
- 不应出现 `ImportError: cannot import name 'ALL_BUILTIN_TOOLS'`。
- 不应出现无参 `create_builtin_registry()` 成功注册本地工具的断言。

- [ ] **Step 2: 如果 `test_error_stays_internal` 覆盖缺失，添加 Agent Home 版本错误封装测试**

如果 Task 2 删除旧 dispatcher 错误封装测试后希望保留该覆盖，在 `tests/test_agent_home_tools.py` 追加：

```python
def test_dispatcher_agent_home_errors_stay_internal():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)
    dispatcher = ToolDispatcher(registry)
    plan = ToolPlan(calls=[
        ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": "/no/such/file"}),
    ])

    results = dispatcher.dispatch(plan)

    assert results[0].status == ToolResultStatus.error
    assert "Tool execution error" in results[0].content
    assert "KeyError" in results[0].content
```

然后运行：

```bash
pytest tests/test_agent_home_tools.py::test_dispatcher_agent_home_errors_stay_internal -v
```

Expected:

- 测试通过。

- [ ] **Step 3: 再次运行两个相关测试文件**

Run:

```bash
pytest tests/test_agent_home_tools.py tests/test_builtin_tools.py -v
```

Expected:

- 全部通过。

---

### Task 5: 运行全量测试并提交实现

**Files:**
- Modify: `agent/tools/builtin/__init__.py`
- Modify: `tests/test_agent_home_tools.py`
- Modify: `tests/test_builtin_tools.py`
- Existing user-modified spec remains as-is: `docs/superpowers/specs/2026-06-08-agent-home-only-builtin-registry-design.md`

- [ ] **Step 1: 运行全量测试**

Run:

```bash
pytest -v
```

Expected:

- 全部测试通过。
- 如果存在与本次改动无关的既有失败，记录失败测试名和错误输出，不要声称全部通过。

- [ ] **Step 2: 查看工作区改动**

Run:

```bash
git status --short
```

Expected:

- 至少包含：
  - `M agent/tools/builtin/__init__.py`
  - `M tests/test_agent_home_tools.py`
  - `M tests/test_builtin_tools.py`
  - 用户已修改的 `M docs/superpowers/specs/2026-06-08-agent-home-only-builtin-registry-design.md`
  - 本计划文件 `docs/superpowers/plans/2026-06-08-agent-home-only-builtin-registry.md`

- [ ] **Step 3: 提交代码改动和计划文件**

如果用户希望把已修改 spec 一起提交，则运行：

```bash
git add agent/tools/builtin/__init__.py tests/test_agent_home_tools.py tests/test_builtin_tools.py docs/superpowers/specs/2026-06-08-agent-home-only-builtin-registry-design.md docs/superpowers/plans/2026-06-08-agent-home-only-builtin-registry.md
git commit -m "fix: require agent home client for builtin registry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

如果用户希望保留 spec 的未提交状态，则运行：

```bash
git add agent/tools/builtin/__init__.py tests/test_agent_home_tools.py tests/test_builtin_tools.py docs/superpowers/plans/2026-06-08-agent-home-only-builtin-registry.md
git commit -m "fix: require agent home client for builtin registry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected:

- 提交成功。
- 不要在未确认的情况下覆盖或还原用户对 spec 的修改。

---

## 自检

- Spec 覆盖：
  - 移除本地工具聚合路径：Task 3 删除 `ALL_BUILTIN_TOOLS` 和本地工具导入。
  - 只注册 Agent Home 工具：Task 3 的 `tools` 列表只使用 Agent Home file/terminal 工厂。
  - `home_client` 为空抛 `RuntimeError`：Task 1 测试，Task 3 实现。
  - 工具名保持稳定：Task 1 schema/tool name 测试覆盖。
  - 移除旧无参 registry 测试：Task 2 覆盖。
- 占位扫描：没有 `TBD`、`TODO`、`implement later` 或未展开的“写测试”。
- 类型一致性：`AgentHomeToolClient | None`、`workspace_get_text`、`workspace_put`、`workspace_list`、`workspace_run_command` 与现有 fake/client 接口一致。
