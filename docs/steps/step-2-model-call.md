# 第二步：模型调用通路

## 环节定位

L-Agent 实施计划的第二步。在运行内核骨架基础上，接通模型调用的完整通路：从用户输入到 LLM 响应。实现 before_agent 和 before_model 阶段的核心 steps，完成 BaseModelContext / ModelRequest 的二层上下文构建，接入真实 LLM 客户端。

## 注意事项

- BaseModelContext 是 run 级不变部分，在 before_agent 构建一次；ModelRequest 是 iteration 级动态请求，每轮 before_model 重新构建
- before_agent 的 memory.prefetch 和 tools.snapshot_available_tools 在本步只做空实现占位，真实逻辑在第三步和第四步补充
- context.prepare_with_budget 第一版只做简单截断，不涉及 LLM 压缩摘要（压缩策略后续独立设计）
- LLM 客户端采用 OpenAI-compatible 接口，首先确保支持 DeepSeek 模型，同时兼容 Claude / GPT / 本地模型
- 本步结束后 Agent 只能做纯对话（无工具），工具通路在第三步接通
- 预算是否允许调用模型不放在 before_model，而放到 model_call middleware（budget.guard）

## 详细内容

### 2.1 上下文数据结构

模型上下文拆为两层：

**BaseModelContext**（run 级不变部分，before_agent 构建）：

- guidance：Agent 静态提示词，包含身份定义和行为原则
- workspace_context：工作目录、项目说明、规则文件等静态上下文
- memory_context：memory.prefetch 的召回结果（本步为空占位）
- available_tools：tools.snapshot 的结果（本步为空占位）
- model_config：模型名称、temperature、max_tokens 等配置

**ModelRequest**（iteration 级动态请求，before_model 构建）：

- messages：本轮发给模型的完整消息列表
- tools：本轮可用工具 schema 列表
- model：模型标识
- temperature / max_tokens：模型参数

### 2.2 LLM 客户端

- `LLMClient` 接口：call(model_request) → ModelResponse
- OpenAI-compatible 实现（支持 /v1/chat/completions 协议）
- **首先确保支持 DeepSeek 模型**（DeepSeek API 兼容 OpenAI 协议，作为首要验证对象）
- `ModelResponse` 类型：
  - content：文本回复
  - tool_calls：工具调用请求列表（可为空）
  - usage：input_tokens / output_tokens
  - finish_reason：stop / tool_calls / length

### 2.3 before_agent 相关 steps

本步实现的 before_agent steps：

- `context.initialize`：创建 RunContext 基础字段，初始化空的 iterations 列表
- `input.normalize`：规范化用户输入（去首尾空白、记录原始输入）
- `base_context.load_static_parts`：加载 guidance / workspace 静态上下文，写入 ctx.base_model_context
- `memory.prefetch`：占位实现，ctx.base_model_context.memory_context = None
- `tools.snapshot_available_tools`：占位实现，ctx.base_model_context.available_tools = []
- `budget.initialize`：初始化预算状态（最大轮数、token 限额、当前消耗）

before_agent 的完整职责定义：

> 创建本次 AgentRun 的运行边界，提交用户输入 checkpoint，并准备本次 run 内不变的 base model context。

### 2.4 before_model steps

本步实现的 before_model steps：

- `iteration.create`：递增 iteration_index，记录到 ctx.iterations
- `messages.collect_visible`：从内存 message list 收集本轮可见消息（第一轮只有 user message，后续轮包含 assistant + tool results）
- `context.prepare_with_budget`：检查消息总 token 是否超窗口，超则截断尾部保留最近消息（第一版简单策略）
- `model_request.compose`：合并 base_model_context（guidance/memory/tools）+ visible messages + model params → 写入 ctx.current_model_request

before_model 的完整职责定义：

> 为当前 ReActIteration 构建一次具体的 ModelRequest。

### 2.5 model_call

结构：

```
model_call:
  middleware:
    - budget.guard
    - timeout.guard
    - trace.record
  action:
    - llm.call
```

- `budget.guard`：检查 ReAct 最大轮数 / 模型调用预算；如果预算耗尽，不执行 action，触发 AgentRun 结束
- `timeout.guard`：控制模型调用超时，超时则中断并标记失败
- `trace.record`：记录耗时、usage、请求元信息（不污染 message list）
- `llm.call`：使用 ctx.current_model_request 调用 LLMClient，写入 ctx.current_model_response

AgentRunner 自动记录 runtime checkpoint：

- model_call_started
- model_call_completed / model_call_failed

### 2.6 after_model steps

本步实现的 after_model steps：

- `model.capture_response`：将 raw model response 写入 ctx.current_model_response
- `usage.update`：累计 token 消耗到 ctx 的 budget/usage 状态
- `result.detect_final_answer`：如果 model_response 没有 tool_calls，则把 content 设置为 ctx.final_result，本次 ReAct loop 准备结束

after_model 的完整职责定义：

> 把模型响应解释为 AgentRun 状态变化。

## Todo List

| # | 任务 | 状态 |
|---|------|------|
| 2.1 | 定义 `BaseModelContext` 数据结构 | done |
| 2.2 | 定义 `ModelRequest` 数据结构 | done |
| 2.3 | 定义 `ModelResponse` 数据结构（content / tool_calls / usage / finish_reason） | done |
| 2.4 | 实现 `LLMClient` 接口 | done |
| 2.5 | 实现 OpenAI-compatible LLMClient | done |
| 2.6 | 实现 step `context.initialize` | done |
| 2.7 | 实现 step `input.normalize` | done |
| 2.8 | 实现 step `base_context.load_static_parts` | done |
| 2.9 | 实现 step `memory.prefetch`（占位） | done |
| 2.10 | 实现 step `tools.snapshot_available_tools`（占位） | done |
| 2.11 | 实现 step `budget.initialize` | done |
| 2.12 | 实现 step `iteration.create` | done |
| 2.13 | 实现 step `messages.collect_visible` | done |
| 2.14 | 实现 step `context.prepare_with_budget`（简单截断） | done |
| 2.15 | 实现 step `model_request.compose` | done |
| 2.16 | 实现 model_call action `llm.call` | done |
| 2.17 | 实现 middleware `budget.guard` | done |
| 2.18 | 实现 middleware `timeout.guard` | done |
| 2.19 | 实现 middleware `trace.record` | done |
| 2.20 | 实现 step `model.capture_response` | done |
| 2.21 | 实现 step `usage.update` | done |
| 2.22 | 实现 step `result.detect_final_answer` | done |
| 2.23 | 编写集成测试：输入 → 完整生命周期 → LLM → 回复输出 | done |
| 2.24 | 编写单元测试：budget.guard 超限阻止调用 | done |
| 2.25 | 编写单元测试：timeout.guard 超时中断 | done |

## 交付与验收标准

- [x] 输入一句话，能经过完整生命周期到达 LLM，获取回复并输出
- [x] BaseModelContext 在 before_agent 构建一次，后续 iteration 复用不重建
- [x] ModelRequest 在每轮 before_model 重新构建
- [x] budget.guard 在轮数超限时阻止模型调用，AgentRun 正常结束
- [x] timeout.guard 在超时时中断模型调用
- [x] trace.record 正确记录 usage 和耗时
- [x] 无 tool_calls 时一轮结束，ctx.final_result 被正确设置
- [x] AgentRun 状态为 completed
- [x] 所有测试通过
