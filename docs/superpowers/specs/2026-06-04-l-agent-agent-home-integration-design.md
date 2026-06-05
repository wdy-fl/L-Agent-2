# L-Agent 接入 Agent-Home 设计规格

## 1. 背景与目标

Agent-Home 第一版已经定义并实现本地 REST daemon，用于承载 L-Agent 的三条状态线：session timeline、logical workspace、long-term memory。L-Agent 现在仍把 timeline 持久化在本地 SQLite，并且内置文件工具直接读写本机文件系统。下一步目标是让 L-Agent 通过 Agent-Home 访问这三类状态能力，把状态管理从 L-Agent core 中移出。

本设计目标：

- L-Agent 运行时和 CLI 主路径完全接入 Agent-Home，不再以本地 `SQLiteTimelineStore` 作为状态主路径。
- Timeline、workspace、memory 三条线都通过统一 client 访问 Agent-Home。
- L-Agent 启动时自动初始化 `agent_id + token`，但不托管 Agent-Home daemon 生命周期。
- Memory 自动提取只在配置允许时触发，不在 `after_agent` 无条件同步长期记忆。
- Workspace 是 agent 的沙箱环境，agent 的文件类操作和命令执行都必须限制在自己的 Agent-Home workspace 内。

## 2. 非目标

本次接入不做以下内容：

- 不让 L-Agent 启动、守护或重启 Agent-Home daemon。
- 不保留 SQLite timeline 作为 CLI fallback。
- 不设计 workspace 本地挂载、FUSE 或本机目录映射。
- 不允许 terminal 工具绕过 Agent-Home workspace 沙箱直接操作宿主机项目目录。
- 不实现 memory 自动提取质量优化；第一版只接通接口和触发策略。
- 不实现 workspace 版本化或 workspace rewind。
- 不改变 L-Agent 的 model/tool 调用编排职责。

## 3. 总体方案

采用“统一 `AgentHomeClient` + 适配现有 L-Agent 状态接口”的方案。

```text
L-Agent CLI / Runner / Steps / Tools
          |
          v
    AgentHomeClient
      - timeline store compatible methods
      - workspace logical object methods
      - memory CRUD/search/extraction methods
          |
          v
Agent-Home REST daemon
      - /v1/agents/{agent_id}/sessions/...
      - /v1/agents/{agent_id}/workspace/...
      - /v1/agents/{agent_id}/memory/...
```

L-Agent 仍负责：

- agent run 生命周期编排；
- model/tool 调用；
- 何时创建 run、message、checkpoint；
- 何时 resume / rewind；
- 何时触发 memory prefetch 和 extraction。

Agent-Home 负责：

- timeline、workspace、memory 的持久化；
- `agent_id + token` 鉴权；
- branch/resume/rewind 的状态查询和更新；
- workspace 逻辑路径到私有对象存储的映射；
- memory CRUD、搜索、候选和自动提取接口。

## 4. 配置与自动初始化

L-Agent 增加 `agent_home` 配置段：

```yaml
agent_home:
  enabled: true
  base_url: "http://127.0.0.1:8765"
  agent_id: ""
  token: ""
  auto_create_agent: true
  auto_extract_memory: false
```

字段语义：

- `enabled`：是否启用 Agent-Home。接入后 CLI 主路径默认启用。
- `base_url`：Agent-Home daemon 地址。
- `agent_id`：Agent-Home 的隔离根 scope。为空时，L-Agent 根据稳定项目标识生成默认值，例如 `l-agent:<project_root_hash>`。
- `token`：该 agent 的 bearer token。token 首次创建后必须写回配置，后续连接用同一组 `agent_id + token` 证明这是同一个 agent。
- `auto_create_agent`：token 为空时是否自动调用 `POST /v1/agents` 创建 agent。
- `auto_extract_memory`：run 完成后是否尝试触发 memory extraction。

身份连续性原则：

- Agent-Home 不推断两次连接是否来自同一个 agent，只校验请求中的 `agent_id` 和 bearer token 是否匹配。
- L-Agent 必须持久化稳定的 `agent_id + token`。同一项目后续启动读取同一组凭证，才能连接到同一个 Agent-Home Home。
- 默认 `agent_id` 不能每次随机生成；应由项目根目录等稳定输入派生，或由用户显式配置。
- token 写回配置失败时，L-Agent 必须启动失败，不能继续进入正常运行，否则下次启动会丢失 agent 身份。

启动流程：

1. `load_settings()` 读取配置。
2. 如果 `agent_id` 为空，根据稳定项目标识生成默认 `agent_id`。
3. CLI 创建 `AgentHomeClient`。
4. 如果 `token` 为空且 `auto_create_agent=true`，调用 `POST /v1/agents` 创建 agent。
5. 创建成功后，把 `agent_id` 和 token 写回当前配置文件。
6. 如果已有 token，调用 `GET /v1/agents/{agent_id}` 验证连接和鉴权。
7. 如果 Agent-Home 未启动、鉴权失败或自动创建失败，L-Agent 启动失败并给出明确提示。

异常处理规则：

- token 为空但 `agent_id` 已存在时，Agent-Home 会返回 `agent_exists`；L-Agent 不自动覆盖或新建身份，应提示用户恢复 token 或换用新的 `agent_id`。
- token 已存在但验证失败时，L-Agent 不自动创建新 agent，应提示用户检查配置。
- 自动创建成功但配置写回失败时，L-Agent 启动失败，避免产生无法再次连接的孤立 Home。

L-Agent 不自动启动 Agent-Home daemon。用户或外部脚本需要先启动服务。

## 5. Timeline 接入

`AgentHomeClient` 实现现有 `TimelineStore` 接口方法，使 runner 和 step 的改动保持最小：

```text
create_session / get_session / update_session / list_sessions
create_branch / get_branch / update_branch
create_run / get_run / update_run_status / get_latest_run_by_branch
append_message / get_messages_by_branch / get_latest_sequence
create_checkpoint / get_checkpoint / get_checkpoints_by_branch / get_latest_stable_checkpoint
```

同时提供 Agent-Home 原生语义方法：

```text
resume(session_id)
rewind(session_id, checkpoint_id)
```

### 5.1 CLI 改动

- `CLISession` 接收 `AgentHomeClient`，不再接收 `SQLiteTimelineStore`。
- `/new` 调用 client 创建 session，使用 Agent-Home 返回的 default branch。
- `/resume` 调用 Agent-Home resume API，更新当前 session 和 branch。
- `/rewind` 调用 Agent-Home rewind API，更新当前 branch。
- `/status` 继续通过 branch messages 统计 turns。
- CLI 主路径不再创建或依赖 `workspace/timeline.db`。

### 5.2 Runner 与 Step 改动

`RunContext.timeline_store` 字段暂时保留，实际对象改为 `AgentHomeClient`。这样以下现有 step 可以继续通过接口工作：

- `RunCreate`
- `MessageCommitUser`
- `MessageCommitAssistant`
- `MessageCommitToolResults`
- runtime checkpoint 记录逻辑

需要补充 after-agent 收尾 step：

1. 根据 `ctx.status` 调用 `update_run_status`。
2. 如果 run completed，则更新当前 branch 的 `resume_head`。
3. 如果 run failed 或 interrupted，不更新 `resume_head`。
4. timeline 写入失败时当前 run 失败，不 fallback 到 SQLite。

## 6. Workspace 沙箱接入

Agent-Home workspace 是 agent 的沙箱环境。L-Agent 暴露给 agent 的所有文件类工具和命令执行工具都必须受这个 workspace 边界约束，不能直接读写宿主机项目目录。

### 6.1 文件工具

L-Agent 内置文件工具改为 Agent-Home workspace 逻辑文件工具。

工具映射：

```text
read_file(file_path, offset, limit)
  -> GET /v1/agents/{agent_id}/workspace/object?path=<logical_path>

write_file(file_path, content)
  -> PUT /v1/agents/{agent_id}/workspace/object?path=<logical_path>

list_directory(path, recursive, pattern)
  -> GET /v1/agents/{agent_id}/workspace/objects?prefix=<logical_path_prefix>

search_file(pattern, path, file_pattern)
  -> list workspace objects, then GET matching file contents and run regex locally
```

路径语义：

- 工具参数名暂时保持 `file_path` / `path`，减少模型提示和既有测试改动。
- 参数描述必须明确：这是 Agent-Home workspace 的逻辑路径，不是本机文件系统路径。
- 逻辑路径必须以 `/` 开头，例如 `/notes/todo.md`、`/artifacts/result.json`。
- 不支持本地相对路径。
- 不支持 `..`。
- 不暴露 Agent-Home 私有对象目录。

### 6.2 Terminal 工具

`terminal` 工具不能继续直接在宿主机项目目录执行。它必须变成 workspace 沙箱命令执行工具。

第一版采用“物理执行目录由 Agent-Home 管理、逻辑 workspace 由 Agent-Home 同步”的方式：

1. Agent-Home 为每个 `agent_id` 维护一个私有 execution root。
2. L-Agent 调用 terminal 前，把命令提交给 Agent-Home 的 command execution API。
3. Agent-Home 在该 agent 的 execution root 内执行命令。
4. 命令执行前，Agent-Home 把当前逻辑 workspace materialize 到 execution root。
5. 命令执行后，Agent-Home 扫描 execution root 的文件变更并写回逻辑 workspace。
6. L-Agent 只拿到 stdout、stderr、exit_code 和结构化错误，不直接接触 execution root。

需要补充 Agent-Home API：

```text
POST /v1/agents/{agent_id}/workspace/commands
```

请求：

```json
{
  "command": "...",
  "timeout_seconds": 120,
  "env": {}
}
```

响应：

```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "changed_paths": ["/notes/todo.md"]
}
```

沙箱约束：

- command 的 cwd 固定为 Agent-Home 管理的 execution root。
- L-Agent 不允许向 terminal 传入宿主机 cwd。
- Agent-Home 必须拒绝或隔离对 execution root 之外路径的写入。
- 第一版不承诺强安全容器隔离；它提供的是 workspace 边界和路径隔离，不是抵抗恶意本机代码的安全沙箱。
- 高风险命令仍保留用户确认机制。

### 6.3 工具注册

实现方式：

- 新增 `create_agent_home_file_tools(client)`，生成绑定 `AgentHomeClient` 的 file tool specs。
- 新增 `create_agent_home_terminal_tool(client)`，把 terminal 调用转发到 Agent-Home command execution API。
- `create_builtin_registry()` 支持传入 `AgentHomeClient`。
- CLI 主路径传入 client 后，只注册 Agent-Home 版本 file tools 和 terminal tool。
- 本地 file tools 和本地 terminal tool 不再作为 CLI 主路径使用。

## 7. Memory 接入

`AgentHomeClient` 增加 memory 方法：

```text
search_memory(q, type=None, tags=None)
create_memory(type, content, tags=None, source_session_id="", source_message_ids=None, confidence=1.0)
update_memory(memory_id, content=None, tags=None)
delete_memory(memory_id)
extract_memory(session_id, trigger)
```

### 7.1 MemoryPrefetch

`MemoryPrefetch` 从 Agent-Home 查询 active memory，并注入模型上下文：

1. 使用当前用户输入作为 `q`。
2. 查询前 N 条 memory。
3. 拼成简短 memory context。
4. 写入 `ctx.base_model_context.memory_context`。
5. 没有结果时保持 `None`。

第一版不引入复杂召回策略，避免把 memory 质量优化和接入工作耦合。

### 7.2 CLI memory 命令

新增 memory 相关 slash commands：

```text
/memory add <content>
/memory search <query>
/memory extract
```

语义：

- `/memory add` 手动写入 Agent-Home memory。
- `/memory search` 查询当前 agent 的 active memory。
- `/memory extract` 对当前 session 显式触发 extraction。

### 7.3 自动提取触发

run 完成后，只有同时满足以下条件才触发 extraction：

- `agent_home.auto_extract_memory=true`；
- 当前 session_id 存在；
- Agent-Home config 允许 auto extract。

如果 Agent-Home 返回 `auto_extract_disabled`，L-Agent 只提示或记录该状态，不把 run 标记为失败。

默认配置不触发自动提取，避免无条件在 `after_agent` 同步长期记忆。

## 8. 错误处理

`AgentHomeClient` 统一解析 Agent-Home 结构化错误：

```json
{
  "error": {
    "code": "invalid_path",
    "message": "path must be absolute and cannot contain '..'",
    "details": {}
  }
}
```

转换为：

```text
AgentHomeError(code, message, details)
```

处理原则：

- `auth_failed`：CLI 提示检查 `agent_id` 和 token。
- 连接失败：CLI 提示先启动 Agent-Home daemon。
- timeline 写入失败：当前 run 失败，不 fallback SQLite。
- `auto_extract_disabled`：作为 memory extraction 的可预期状态处理。
- workspace/memory tool 错误：返回包含错误码和 message 的文本给模型。

## 9. 测试与验收标准

### 9.1 Client 自动初始化

- token 为空且 `auto_create_agent=true` 时，自动调用 `POST /v1/agents`。
- 创建成功后 token 写回 L-Agent 配置。
- token 已存在时，调用 `GET /v1/agents/{agent_id}` 验证。
- Agent-Home 结构化错误能解析为 `AgentHomeError`。
- Agent-Home 未启动时，CLI 启动失败并给明确提示。

### 9.2 Timeline

- 新 session 自动拥有 default branch。
- 完整 run 写入 user、assistant、tool messages。
- runtime checkpoint 正常写入。
- completed run 更新 `resume_head`。
- failed/interrupted run 不更新 `resume_head`。
- resume 能恢复 active branch 上下文。
- rewind 到 user snapshot 后创建新 branch。
- rewind 后上下文包含该 user message，不包含后续 assistant/tool。
- CLI 主路径不创建或依赖 `workspace/timeline.db`。

### 9.3 Workspace

- 逻辑路径 `/notes/todo.md` 可写、读、列出、搜索。
- 逻辑路径 `/artifacts/result.json` 可正常保存工具产物。
- 非 `/` 开头路径返回 `invalid_path`。
- 包含 `..` 的路径返回 `invalid_path`。
- 本地文件系统不会出现对应逻辑文件。
- terminal 命令通过 Agent-Home command execution API 执行。
- terminal 命令的 cwd 固定在 Agent-Home 管理的 execution root。
- terminal 创建或修改的文件会写回 Agent-Home 逻辑 workspace。
- L-Agent CLI 主路径不注册本地 terminal tool。

### 9.4 Memory

- `MemoryPrefetch` 能把 search 结果注入 model context。
- `/memory add` 可写入 memory。
- `/memory search` 可查询 memory。
- `/memory extract` 可显式触发 extraction。
- `auto_extract_memory=false` 时 run 完成不触发 extraction。
- `auto_extract_memory=true` 且 Agent-Home config 允许时，run 完成后触发 extraction。
- `auto_extract_disabled` 不导致 run 失败。

## 10. 迁移影响

迁移后，L-Agent 的状态主路径从本地 SQLite 变为 Agent-Home REST API。

需要调整的主要区域：

- `agent/config/settings.py`：增加 `agent_home` 配置。
- `agent/home/client.py`：新增 Agent-Home client。
- `agent/cli/app.py`：初始化 client，移除 SQLiteTimelineStore 主路径。
- `agent/cli/commands.py`：session 和 memory 命令改走 client。
- `agent/core/factory.py`：创建绑定 client 的 tools 和 steps。
- `agent/steps/*`：补充 run 收尾、memory prefetch、必要的 client 注入。
- `agent/tools/builtin/file_ops.py`：拆分或替换为 Agent-Home workspace file tools。
- `agent/tools/builtin/terminal.py`：替换为 Agent-Home workspace command tool。
- `Agent-Home/agent_home/workspace.py`：补充 workspace command execution API。
- `tests/*`：把 timeline/workspace/memory/terminal 主路径测试迁移到 Agent-Home client。

`SQLiteTimelineStore` 可以暂时保留给旧测试或对照，但 CLI 和运行时主路径不再使用它。

## 11. 一致性原则

1. L-Agent 不直接读写 Agent-Home 私有对象目录。
2. L-Agent 不把 workspace 逻辑路径解释为本机路径。
3. L-Agent 暴露给 agent 的文件工具和 terminal 工具都必须受 Agent-Home workspace 沙箱约束。
4. L-Agent CLI 主路径不注册会绕过 workspace 沙箱的本地文件或本地 terminal 工具。
5. L-Agent 不在 Agent-Home 不可用时 fallback 到 SQLite timeline。
6. L-Agent 不无条件在 `after_agent` 同步长期记忆。
7. Agent-Home 仍是状态服务，L-Agent 仍是运行时编排者。
8. 所有 Agent-Home 请求都必须带 `agent_id` 和 bearer token。
9. failed/interrupted run 不更新 `resume_head`。
10. memory extraction 的不可用状态不影响正常 agent run 完成。
