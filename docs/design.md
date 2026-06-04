# L-Agent 第一版宏观设计

> L-Agent 是 F-Agent 2.0 重构版：保留本地 CLI 个人 Agent 的定位，但重新抽象 Agent 的运行生命周期、Step 扩展边界，以及 Session / Branch / Checkpoint 时间线模型。

## 1. 设计定位

L-Agent 不以通用 Agent Framework 或多端产品平台为第一目标。第一版目标是：

- 将 F-Agent 中偏重的 AgentLoop 拆解为清晰的运行内核。
- 用固定生命周期表达 AgentRun 的运行语义。
- 让生命周期阶段内的 Step 可插拔、可扩展、可测试。
- 用 Branch / Checkpoint 支撑类似 Claude Code 的 resume 和 rewind 能力。
- 为后续持久化记忆、上下文压缩、A2A 多 Agent 协议预留边界，但不在第一版展开。

核心方向采用统一内核方案：

```text
AgentRunner
固定八段 Lifecycle
Step Registry
Action Middleware
RunContext
Session / Branch / AgentRun / ReActIteration
Checkpoint
```

## 2. 核心概念

### 2.1 Agent

Agent 是一个完整运行主体，不只是一次 LLM 调用器。

```text
Agent
├── guidance
├── AgentRunner
├── StepRegistry
├── Middleware
├── ToolRegistry
├── Memory interface
├── Skill interface
├── SessionStore
└── Workspace
```

定义：

> Agent 是一个围绕输入运行固定生命周期、通过模型决策和工具行动推进任务，并在会话时间线上沉淀上下文状态的运行主体。

### 2.2 Session

Session 是长期会话容器，表示用户可感知的一次连续工作上下文。

```text
Session
├── session_id
├── title
├── active_branch_id
├── created_at / updated_at
└── metadata / stats
```

Session 不直接等于一条线性消息历史；它更像一个容器，内部可以有多条 Branch。

### 2.3 Branch

Branch 是 Session 内的一条上下文时间线。

```text
Session
└── Branch*
    ├── parent_branch_id
    ├── fork_checkpoint_id
    ├── base_message_cursor
    ├── resume_head
    └── messages / runs / checkpoints
```

正常对话追加到 active branch。Rewind 不删除旧历史，而是从某个 `user_message_committed` checkpoint 创建新 branch。

### 2.4 AgentRun

AgentRun 是 Agent 响应一次输入的完整运行事务。

```text
Session
└── Branch
    └── AgentRun*
```

一次 AgentRun 包含：

- 一次输入
- 一个 RunContext
- 一个固定生命周期
- 多轮 ReActIteration
- 最终 completed / failed / interrupted 状态

AgentRun 是生命周期边界。

### 2.5 ReActIteration

ReActIteration 是 AgentRun 内的一轮模型决策与可选工具行动。

```text
AgentRun
└── ReActIteration*
    ├── before_model
    ├── model_call
    ├── after_model
    ├── before_tool?
    ├── tool_call?
    └── after_tool?
```

如果模型没有 tool_calls，则本轮产生最终回复，AgentRun 进入 `after_agent`。

### 2.6 Checkpoint

Checkpoint 是 Branch 时间线上的恢复边界，分为两类语义。

```text
Checkpoint
├── user snapshot checkpoint
└── runtime checkpoint
```

第一版唯一用户可见 checkpoint：

```text
user_message_committed
```

它用于 rewind。

Runtime checkpoint 默认不作为用户 rewind 点，只用于内部恢复、诊断和副作用安全判断，例如：

```text
model_call_started
model_call_completed
assistant_message_committed
tool_call_started
tool_call_completed
tool_results_committed
run_completed
run_failed
run_interrupted
```

### 2.7 Resume 与 Rewind

Resume：

```text
恢复 active branch 最新完整运行结果。
```

也就是恢复到最近的 `run_completed` 对应状态，用于“接着聊”。

Rewind：

```text
回到某个 user_message_committed checkpoint，并创建新 branch。
```

Rewind 后，新 branch 上下文包含该 user message，但不包含它之后的 assistant/tool 结果。

### 2.8 多 Agent

多 Agent 不采用子 Agent 从属模型，而是 A2A 对等交互：

```text
Agent A ←A2A Protocol→ Agent B
```

每个 Agent 都是完整 Agent。A2A 后续作为协议能力接入，不进入第一版核心生命周期。

## 3. 固定八段生命周期

L-Agent 第一版生命周期固定，不通过配置增删阶段。

```text
AgentRun
├── before_agent
├── ReActIteration*
│   ├── before_model
│   ├── model_call
│   ├── after_model
│   ├── before_tool?
│   ├── tool_call?
│   └── after_tool?
└── after_agent
```

规则：

- `before_agent` / `after_agent` 是 run 级阶段，每次 AgentRun 只执行一次。
- `before_model` / `model_call` / `after_model` 是 iteration 级阶段，每轮 ReAct 都执行。
- `before_tool` / `tool_call` / `after_tool` 只有模型返回 tool_calls 时执行。
- Hook Phase 固定，Phase 内部的 Step 可注册、启用、禁用、调参、排序。
- `model_call` 和 `tool_call` 是固定 Action + Middleware，不作为普通 Step。

## 4. RunContext 与模型上下文

一次 AgentRun 有一个全局可变 RunContext。

```text
RunContext
├── session / branch / run
├── input
├── base_model_context
├── iterations
├── current_model_request
├── current_model_response
├── current_tool_plan
├── current_tool_results
├── final_result
├── errors
└── runtime state
```

模型上下文拆为两层：

```text
BaseModelContext  # run 级不变部分
ModelRequest      # iteration 级动态请求
```

`BaseModelContext` 在 `before_agent` 构建：

```text
guidance
workspace static context
normalized user input metadata
memory.prefetch result
available tools snapshot
model config
```

`ModelRequest` 在每轮 `before_model` 构建：

```text
base_model_context
visible messages
compression/budget prepared context
available tools
current model params
```

## 5. 各阶段 Step 分布

### 5.1 before_agent

职责：

> 创建本次 AgentRun 的运行边界，提交用户输入 checkpoint，并准备本次 run 内不变的 base model context。

Steps：

```text
before_agent:
  - run.create
  - branch.resolve_active
  - context.initialize
  - input.normalize
  - message.commit_user
  - checkpoint.create_user_snapshot
  - base_context.load_static_parts
  - memory.prefetch
  - tools.snapshot_available_tools
  - budget.initialize
```

说明：

- `message.commit_user` 和 `checkpoint.create_user_snapshot` 共同形成用户可见 rewind 边界。
- `memory.prefetch` 只在 run 开始时做一次，基于本次输入召回 run 级记忆。
- `tools.snapshot_available_tools` 只在 run 开始时确定本次 run 可用工具集合。
- 第一版不做每轮 memory refresh 或 dynamic tool filtering。

### 5.2 before_model

职责：

> 为当前 ReActIteration 构建一次具体的 ModelRequest。

Steps：

```text
before_model:
  - iteration.create
  - messages.collect_visible
  - context.prepare_with_budget
  - model_request.compose
```

说明：

- `messages.collect_visible` 从当前 Branch 时间线收集本轮可见 messages。
- `context.prepare_with_budget` 负责保证上下文符合模型窗口，但具体压缩策略后续单独设计。
- `model_request.compose` 合并 base context、visible messages、tools snapshot 和模型参数。
- 预算是否允许调用模型不放这里，而放到 `model_call` middleware。

### 5.3 model_call

职责：

> 执行一次模型调用，并由 middleware 控制调用边界。

结构：

```text
model_call:
  middleware:
    - budget.guard
    - timeout.guard
    - trace.record
  action:
    - llm.call
```

AgentRunner 自动记录 runtime checkpoint：

```text
model_call_started
model_call_completed
model_call_failed
```

说明：

- `budget.guard` 控制 ReAct 最大轮数 / 模型调用预算。
- `timeout.guard` 控制模型调用超时。
- `trace.record` 记录耗时、usage、请求元信息。
- `llm.call` 使用 `ctx.current_model_request`，写入 `ctx.current_model_response`。

### 5.4 after_model

职责：

> 把模型响应解释为 AgentRun 状态变化。

Steps：

```text
after_model:
  - model.capture_response
  - message.commit_assistant
  - usage.update
  - result.detect_final_answer
  - tool.detect_requested
```

内部 runtime checkpoint：

```text
assistant_message_committed
```

说明：

- 即使 assistant message 包含 tool_calls，也必须进入 message timeline。
- 如果没有 tool_calls，则 `result.detect_final_answer` 设置 `ctx.final_result`，本次 ReAct loop 准备结束。
- 如果有 tool_calls，则 `tool.detect_requested` 标记进入工具段。

### 5.5 before_tool

职责：

> 把模型请求的 tool_calls 转换成可执行、可审计、可安全处理的 ToolPlan。

Steps：

```text
before_tool:
  - tool_calls.extract
  - tool_calls.parse_arguments
  - tool_calls.validate_schema
  - tool_calls.resolve_tools
  - tool_plan.build_serial
  - approval.prepare_requests
```

说明：

- before_tool 做计划级解析与校验。
- ToolDispatcher 仍做最终防御性校验。
- 第一版工具执行保持全串行，不做 parallel_safe。
- `approval.prepare_requests` 只准备审批上下文，不真正执行审批阻断。

### 5.6 tool_call

职责：

> 按 ToolPlan 串行执行工具，或在审批拒绝时生成拒绝类 tool result。

结构：

```text
tool_call:
  middleware:
    - approval.guard
    - audit.record
    - result_limit.guard
  action:
    - tools.dispatch_serial
```

AgentRunner 自动记录 runtime checkpoint：

```text
tool_call_started
tool_call_completed
tool_call_failed
```

说明：

- `approval.guard` 真正决定放行或拒绝。
- 如果用户拒绝或策略拒绝，不终止 AgentRun，而是生成 denied tool result。
- `audit.record` 记录工具执行审计。
- `result_limit.guard` 统一限制工具结果大小。
- `tools.dispatch_serial` 按 ToolPlan 顺序执行，并做最终防御校验。

### 5.7 after_tool

职责：

> 把工具执行结果提交为下一轮 ReAct 可见的 observation。

Steps：

```text
after_tool:
  - tool_results.capture
  - message.commit_tool_results
  - checkpoint.record_tool_results_committed
```

说明：

- 每个 tool result 都写成 `role=tool` message，并保留 `tool_call_id`。
- `tool_results_committed` 是内部 runtime checkpoint，不是用户 rewind 点。
- 不在 after_tool 做上下文压缩；压缩/裁剪放到下一轮 `before_model`。

### 5.8 after_agent

职责：

> 结束本次 AgentRun，提交 run 级状态，并更新 resume 所需的 branch head。

Steps：

```text
after_agent:
  - result.finalize
  - run.mark_terminal_state
  - checkpoint.record_run_terminal_state
  - branch.update_resume_head
  - stats.update_session
  - cleanup.release_runtime_state
```

说明：

- `branch.update_resume_head` 只在 run completed 时更新。
- resume 恢复 active branch 最新完整运行结果。
- 第一版不在 after_agent 自动执行 `memory.sync`。
- 持久化记忆管理机制后续单独设计。
- 上下文压缩策略后续单独设计。

## 6. Step、Registry 与配置

### 6.1 Step 类接口

Step 第一版采用类接口式：

```python
class Step:
    name: str
    phase: HookPhase

    def run(self, ctx: RunContext) -> None:
        ...
```

第一版不做复杂 `depends_on / config_schema / plugin metadata`，但保留后续扩展空间。

### 6.2 StepRegistry

StepRegistry 负责：

```text
- 注册 Step
- 按 phase 收集 Step
- 按配置启用/禁用 Step
- 按配置调整 Step 顺序
- 为 AgentRunner 提供 phase -> steps
```

概念接口：

```text
StepRegistry
├── register(step)
├── get_steps(phase)
└── configure(config)
```

### 6.3 配置策略

第一版采用：

> 代码注册为主，配置只控制 Step 的行为。

配置不负责重写生命周期，只做：

```text
- Step enabled / disabled
- Step 参数
- Step 局部顺序
```

示例：

```yaml
steps:
  memory.prefetch:
    enabled: true
    limit: 5

  tools.snapshot_available_tools:
    enabled: true

  context.prepare_with_budget:
    strategy: simple
```

配置能力可以分阶段推进：

```text
第一阶段：只支持 enabled 和参数。
第二阶段：支持 order / before / after。
第三阶段：支持外部插件注册新 step。
```

## 7. Action 与 Middleware

`model_call` 和 `tool_call` 不作为普通 Step。它们是固定 Action，由 Middleware 包裹。

```text
Action:
  - llm.call
  - tools.dispatch_serial
```

Middleware 第一版可以采用轻量接口：

```python
class Middleware:
    name: str
    target: ActionName

    def __call__(self, ctx: RunContext, next_call: Callable) -> Any:
        ...
```

默认：

```text
model_call middleware:
  - budget.guard
  - timeout.guard
  - trace.record

tool_call middleware:
  - approval.guard
  - audit.record
  - result_limit.guard
```

配置只控制 Middleware 的启停和参数，不改变 Action 本身。

## 8. AgentRunner

AgentRunner 是一次 AgentRun 的流程推进器。

职责：

```text
- 创建并持有 RunContext
- 执行 before_agent
- 驱动 ReAct loop
- 执行 before_model / model_call / after_model
- 有 tool_calls 时执行 before_tool / tool_call / after_tool
- 执行 after_agent
- 自动记录 action 边界 runtime checkpoint
- 根据 ctx.final_result / tool_calls / errors 判断流程走向
```

AgentRunner 不负责具体业务：

```text
不直接做 memory
不直接做 tool parsing
不直接做 compression
不直接做 persistence details
```

这些都由 Step、Action、Middleware 或 Store 完成。

## 9. 存储与时间线边界

第一版核心存储概念：

```text
sessions
branches
agent_runs
react_iterations
messages
checkpoints
```

当前设计阶段不展开事务细节，只保留语义要求：

```text
Session:
  会话容器

Branch:
  上下文时间线

AgentRun:
  一次输入到输出的运行事务

ReActIteration:
  一轮模型决策和可选工具行动

Message:
  conversation timeline 的事实记录

Checkpoint:
  恢复边界
```

关键规则：

```text
resume:
  使用 active branch 最新完整 run 状态。

rewind:
  使用 user_message_committed checkpoint 创建新 branch。

user_message_committed:
  第一版唯一用户可见 checkpoint。

runtime checkpoints:
  用于内部恢复、诊断和副作用安全判断。
```

## 10. 第一版暂不展开的内容

以下内容后续单独设计：

```text
- 持久化记忆管理机制
- 上下文压缩具体策略
- A2A 多 Agent 协议
- Step 插件生态
- 工具并行调度
- 复杂事务与恢复修复策略
```

这些内容在第一版设计中只保留清晰边界，不展开实现。

## 11. 自检

- 本设计没有把 F-Agent 现状当作标准答案，而是以 L-Agent 的生命周期语义重新组织 Agent 内核。
- 生命周期固定，避免把 Agent 语义本身配置化。
- 可插拔能力限定在 Hook Phase 内的 Step，以及 Action 外层的 Middleware。
- Resume 与 Rewind 的语义明确区分：resume 到最新完整运行结果，rewind 到用户输入 checkpoint 并创建新 branch。
- 持久化记忆、上下文压缩、A2A、多工具并行和事务细节都被明确推迟，避免第一版设计发散。
