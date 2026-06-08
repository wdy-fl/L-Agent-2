# 仅保留 Agent Home 内置工具注册设计

## 背景

`agent/tools/builtin/__init__.py` 当前以两种模式创建 `ToolRegistry`：

- 未传入 `home_client` 时，注册本地文件工具和本地终端工具。
- 传入 `home_client` 时，注册 Agent Home 工作区文件工具和 Agent Home 沙箱终端工具。

本次需求是移除本地注册模式。内置文件工具和终端工具只能通过 Agent Home 使用。如果缺少 `home_client`，创建注册表时应直接抛出 `RuntimeError`。

## 目标

- 从内置工具注册模块中移除本地工具聚合路径。
- 确保 `create_builtin_registry` 只注册 Agent Home 支持的文件工具和终端工具。
- 未提供 `home_client` 时，明确抛出 `RuntimeError`。
- 保持现有公开工具名不变，使模型/工具调用方仍能看到 `read_file`、`write_file`、`list_directory`、`search_file` 和 `terminal`。
- 移除此前依赖“无 `home_client` 时注册本地工具”行为的测试。

## 非目标

- 除非导入或测试需要，不修改审批策略常量。
- 不修改 Agent Home workspace client 的行为。

## 架构设计

`agent/tools/builtin/__init__.py` 将成为仅面向 Agent Home 的注册入口。

它只应导入组装 Agent Home 工具所需的对象：

- `AgentHomeWorkspace`
- `create_agent_home_file_tools`
- `AgentHomeCommandRunner`
- `create_agent_home_terminal_tool`
- `think_tool`
- `web_search_tool`
- `web_fetch_tool`
- `ToolRegistry`

该模块不应再暴露包含本地工具对象的 `ALL_BUILTIN_TOOLS` 列表。

`create_builtin_registry` 应保留运行时防御检查：

```python
def create_builtin_registry(home_client: AgentHomeToolClient | None = None) -> ToolRegistry:
    if home_client is None:
        raise RuntimeError("Agent Home client is required to create the built-in tool registry.")
    ...
```

完成检查后，只注册以下工具：

1. `think_tool`
2. `create_agent_home_file_tools(home_client)` 返回的所有工具
3. `create_agent_home_terminal_tool(home_client)`
4. `web_search_tool`
5. `web_fetch_tool`

## 数据流

1. 应用初始化阶段获取或构造 Agent Home client。
2. `agent/core/factory.py` 调用 `create_builtin_registry(home_client=home_client)`。
3. 注册表对外暴露的工具名保持不变。
4. 文件操作通过 `home_client.workspace_get_text`、`home_client.workspace_put` 和 `home_client.workspace_list` 执行。
5. 终端操作通过 `home_client.workspace_run_command` 执行。
6. 如果应用初始化时传入 `None`，`create_builtin_registry` 会在返回任何注册表前抛出 `RuntimeError`。

## 错误处理

- 缺少 `home_client` 时抛出 `RuntimeError`，错误信息明确说明必须配置 Agent Home client。
- 现有 Agent Home 文件工具和终端工具的错误行为保持不变。
- Agent Home 搜索工具中的非法正则处理保持不变。

## 测试策略

更新或新增测试，覆盖：

- `create_builtin_registry(home_client=None)` 会抛出 `RuntimeError`。
- 传入 fake Agent Home client 后，注册表包含预期 schema 和工具名。
- `read_file`、`write_file`、`list_directory`、`search_file` 和 `terminal` 会调用 fake Agent Home workspace 方法。

## 实现说明

当前调用点搜索结果显示：

- `agent/core/factory.py` 已经传入 `home_client=home_client`。
- `tests/test_agent_home_tools.py` 已经传入 fake Agent Home client。
- `tests/test_builtin_tools.py` 存在无参 registry 测试，需要更新。

实现时应保留 web 工具和 think 工具，因为它们不是本地文件/终端工作区实现。

## 自检

- 没有遗留占位需求。
- 范围限定在内置工具注册行为和测试。
- 运行时失败模式明确：缺少 `home_client` 时抛出 `RuntimeError`。
- 工具名保持稳定，但实现只来自 Agent Home。
