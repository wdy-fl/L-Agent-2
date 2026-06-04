# L-Agent 实施计划

> 基于第一版宏观设计，将实现分为七个步骤推进。每步有明确的交付内容和验证标准。

## 第一步：运行内核骨架

### 1.1 生命周期定义

- `HookPhase` 枚举：before_agent / before_model / after_model / before_tool / after_tool / after_agent
- `ActionName` 枚举：model_call / tool_call
- 阶段分类标识：run 级 vs iteration 级

### 1.2 RunContext

- 基础字段定义：session / branch / run / input / iterations / errors / runtime state
- 模型相关占位：base_model_context / current_model_request / current_model_response
- 工具相关占位：current_tool_plan / current_tool_results
- 结果相关：final_result / has_tool_calls

### 1.3 Step 基类与 Registry

- `Step` 基类：name / phase / run(ctx)
- `StepRegistry`：register / get_steps(phase) / configure（启停、参数）

### 1.4 Middleware 基类与 Chain

- `Middleware` 基类：name / target / `__call__(ctx, next_call)`
- `MiddlewareChain`：组装 middleware 列表，按洋葱模型包裹 action

### 1.5 AgentRunner

- 创建并持有 RunContext
- 按顺序执行 before_agent → ReAct loop → after_agent
- ReAct loop 内部：before_model → model_call → after_model → (before_tool → tool_call → after_tool)?
- 循环退出条件：ctx.final_result 被设置 / 错误 / 中断
- Action 执行时自动记录 runtime checkpoint（先留接口，不接存储）

### 验证标准

- 注册空 step，AgentRunner 能按正确顺序调用各 phase 的 steps
- Action + Middleware 链能正确执行
- has_tool_calls=False 时跳过工具段、退出循环
- has_tool_calls=True 时进入工具段、继续循环

---

## 第二步：模型调用通路

### 2.1 上下文数据结构

- `BaseModelContext`：guidance / workspace_context / memory_context / available_tools / model_config
- `ModelRequest`：messages / tools / model / temperature / max_tokens

### 2.2 LLM 客户端

- `LLMClient` 接口：call(model_request) → ModelResponse
- OpenAI-compatible 实现（支持 Claude / GPT / 本地模型）
- `ModelResponse` 类型：content / tool_calls / usage / finish_reason

### 2.3 before_agent 相关 steps

- `context.initialize`：创建 RunContext 基础字段
- `input.normalize`：规范化用户输入
- `base_context.load_static_parts`：加载 guidance / workspace 静态上下文
- `budget.initialize`：初始化预算（最大轮数、token 限额）

### 2.4 before_model steps

- `iteration.create`：记录 iteration_index
- `messages.collect_visible`：从内存 message list 收集本轮可见消息
- `context.prepare_with_budget`：第一版简单实现——检查是否超窗口，超则截断尾部
- `model_request.compose`：合并 base_context + messages + tools → ModelRequest

### 2.5 model_call

- Action：`llm.call` — 使用 ctx.current_model_request 调用 LLMClient
- Middleware：`budget.guard`（检查轮数）/ `timeout.guard`（超时控制）/ `trace.record`（记录 usage）

### 2.6 after_model steps

- `model.capture_response`：写入 ctx.current_model_response
- `usage.update`：累计 token 消耗
- `result.detect_final_answer`：无 tool_calls 时设置 ctx.final_result

### 验证标准

- 输入一句话，能经过完整生命周期到达 LLM，获取回复并输出
- budget.guard 在超限时阻止调用
- 无 tool_calls 时一轮结束

---

## 第三步：工具调用通路

### 3.1 工具基础设施

- `ToolSpec`：name / description / parameters_schema / handler
- `ToolCall`：call_id / tool_name / arguments
- `ToolResult`：call_id / status(success/error/denied) / content
- `ToolPlan`：calls 列表 / execution_mode=serial
- `ToolRegistry`：register / get / list_schemas
- `ToolDispatcher`：按 ToolPlan 串行执行，含防御性校验

### 3.2 after_model 补充

- `tool.detect_requested`：有 tool_calls 时设 ctx.has_tool_calls = True

### 3.3 before_tool steps

- `tool_calls.extract`：从 model_response 取出 tool_calls
- `tool_calls.parse_arguments`：JSON string → dict
- `tool_calls.validate_schema`：校验参数
- `tool_calls.resolve_tools`：确认工具存在于 available_tools
- `tool_plan.build_serial`：构建串行执行计划
- `approval.prepare_requests`：标记需要审批的工具（先留接口）

### 3.4 tool_call

- Action：`tools.dispatch_serial` — 按 ToolPlan 执行
- Middleware：`approval.guard`（拒绝时生成 denied result）/ `audit.record` / `result_limit.guard`（截断过长结果）

### 3.5 after_tool steps

- `tool_results.capture`：收集执行结果到 ctx.current_tool_results
- `message.commit_tool_results`：将 tool results 作为 role=tool 消息加入 message list

### 3.6 ReAct 循环闭合

- AgentRunner 在 after_tool 后回到 before_model
- 下一轮 messages.collect_visible 能看到上一轮的 assistant tool_calls + tool results

### 3.7 内置工具：think

- 无副作用的思考工具，验证工具调用通路可用

### 验证标准

- 模型请求 think 工具 → 执行 → 结果回到上下文 → 模型基于结果继续
- 多轮 ReAct 正确循环直到最终回答
- 审批拒绝时生成 denied result，模型收到后调整策略

---

## 第四步：时间线与持久化

### 4.1 数据模型

- `Session`：session_id / title / active_branch_id / created_at / updated_at / metadata
- `Branch`：branch_id / session_id / parent_branch_id / fork_checkpoint_id / base_message_cursor / resume_head
- `AgentRun`：run_id / session_id / branch_id / status / created_at / completed_at
- `ReActIteration`：iteration_id / run_id / index
- `Message`：message_id / session_id / branch_id / run_id / sequence / role / content / tool_call_id
- `Checkpoint`：checkpoint_id / session_id / branch_id / run_id / kind(user_snapshot/runtime) / name / message_cursor / created_at

### 4.2 存储层

- `TimelineStore` 接口：CRUD for session / branch / message / checkpoint / run
- SQLite 实现 + schema 定义

### 4.3 生命周期 steps 接入持久化

- before_agent：`run.create` 写 AgentRun 记录；`message.commit_user` 写 user message；`checkpoint.create_user_snapshot` 写 user_message_committed
- after_model：`message.commit_assistant` 写 assistant message（含 tool_calls 的也写入）
- after_tool：`message.commit_tool_results` 写 tool result messages；`checkpoint.record_tool_results_committed`
- after_agent：`run.mark_terminal_state` 更新 run status；`checkpoint.record_run_terminal_state`

### 4.4 AgentRunner checkpoint 接口落地

- model_call_started / model_call_completed / model_call_failed
- tool_call_started / tool_call_completed / tool_call_failed

### 验证标准

- 一次完整 AgentRun 后，SQLite 中有完整的 session / branch / run / messages / checkpoints 记录
- 消息 sequence 正确，checkpoint 的 message_cursor 正确指向

---

## 第五步：Resume 与 Rewind

### 5.1 Branch 管理

- `branch.resolve_active`：加载 session 的 active branch
- `branch.update_resume_head`：run completed 后更新 branch 的 resume_head
- 创建 session 时自动创建默认 branch

### 5.2 Resume

- 找到 active branch 最新 run_completed 对应的 checkpoint
- 恢复 message_cursor 之前的所有 messages 作为上下文
- 等待用户新输入，开始新 AgentRun

### 5.3 Rewind

- 给定 user_message_committed checkpoint
- 创建新 branch：parent_branch_id / fork_checkpoint_id / base_message_cursor
- 切换 session.active_branch_id 到新 branch
- 恢复上下文：parent branch 中 cursor 之前的消息

### 5.4 before_agent 集成

- `branch.resolve_active`：判断是新 session、resume、还是正常追加
- messages.collect_visible 适配 branch 结构共享（parent messages + own messages）

### 验证标准

- 一次 session 多轮对话后退出，resume 能恢复完整上下文继续
- rewind 到某条用户输入，新 branch 上下文正确（包含该 user message，不包含之后的 assistant/tool）
- 旧 branch 历史保留不变

---

## 第六步：CLI 与用户交互

### 6.1 主循环

- 读取用户输入 → 创建/恢复 session → 启动 AgentRun → 输出结果 → 等待下一轮
- 支持多轮对话

### 6.2 会话管理

- 新建 session
- 列出历史 sessions
- resume 指定 session
- rewind 到指定 checkpoint

### 6.3 工具审批交互

- approval.guard 触发时暂停，向用户展示待执行工具和参数
- 用户确认/拒绝
- 配置 auto-approve 规则

### 6.4 输出展示

- assistant 回复展示
- 工具调用过程展示（工具名、参数、结果摘要）
- 运行状态展示（iteration 数、token 消耗）

### 验证标准

- 作为 CLI 工具能正常交互对话
- 工具审批流程可用
- session resume / rewind 命令可用

---

## 第七步：内置工具补全

### 7.1 文件操作

- read_file / write_file / list_directory / search_file

### 7.2 终端

- terminal（执行 shell 命令）

### 7.3 Web

- web_search / web_fetch

### 7.4 工具统一规范

- 每个工具有完整 ToolSpec（name / description / parameters_schema）
- 错误处理统一格式
- 结果大小限制配合 result_limit.guard

### 验证标准

- 能用 L-Agent 完成日常开发任务：读写文件、执行命令、搜索信息
- 工具结果正确回到模型上下文，驱动多步任务完成

---

## 后续独立设计（不在当前计划细化）

- 持久化记忆管理机制
- 上下文压缩策略
- A2A 多 Agent 协议
- Step 插件生态
- 工具并行调度
- 复杂事务与恢复修复策略
