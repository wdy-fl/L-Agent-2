# 第八步：后续独立设计

## 环节定位

L-Agent 实施计划的第八步。前七步完成后，Agent 具备完整的运行内核、模型调用、工具执行、持久化时间线、Resume/Rewind、CLI 交互和基础工具能力。本步是对第一版设计中明确推迟的高级能力进行独立设计与实施。每个子主题相对独立，可并行或按优先级排序推进。

## 注意事项

- 每个子主题应先单独完成设计讨论，再进入实施，避免在没有设计共识的情况下编码
- 这些能力的设计需要与第一版核心架构保持兼容，不破坏已有的生命周期、Step、Middleware 机制
- 新增能力应通过 Step / Middleware / Action adapter 接入，不修改 AgentRunner 主流程
- 各子主题之间有依赖关系需要注意（见下方说明）
- 本文档只做高层规划，每个子主题启动时应创建独立的设计文档和实施文档

## 详细内容

### 8.1 持久化记忆管理机制

**范围**：

- memory.prefetch 的真实实现（目前为占位）
- 记忆的写入时机与触发条件
- 记忆分类（user / feedback / project / reference 或其他分类方式）
- 记忆与 branch 的关系（全局 vs 分支隔离）
- 记忆索引与检索策略
- 记忆的生命周期管理（过期、更新、删除）

**与核心架构的接入点**：

- before_agent step `memory.prefetch`：基于用户输入召回 run 级记忆
- 记忆写入时机：独立于 after_agent（不在 after_agent 自动 sync，需单独设计触发条件）

**依赖**：无前置依赖，可独立启动

### 8.2 上下文压缩策略（已实现）

**实现方案**：头尾保护 + LLM 结构化摘要 + 迭代压缩（参照 F-Agent 方案）

**核心文件**：

- `agent/context/compressor.py` — `ContextCompressor` 压缩器
- `agent/steps/before_model.py` — `ContextPrepareWithBudget` Step 集成压缩器
- `agent/config/settings.py` — `ContextSettings` 配置

**压缩流程**：

1. 每次 before_model 阶段估算当前 token 数
2. 超过 `context_window * compression_threshold`（默认 50%）时触发压缩
3. 按 tool_calls 约束将消息分为不可拆分的原子组
4. 划分三段：head（前 N 组保护）、tail（最近 M tokens 保护）、middle（可压缩区域）
5. middle 区域工具结果替换为占位符，通过 LLM 生成结构化摘要
6. 支持迭代压缩：识别旧摘要，与新增对话合并生成更新摘要
7. 反抖动：节省不足 `min_saving` 时跳过
8. 压缩后仍超限则 fallback 到 FIFO 截断

**LLM 调用方式**：

压缩 Step 内部的 LLM 调用通过 `middleware_chain.execute(ActionName.model_call, ...)` 执行，复用主模型调用的 middleware pipeline（BudgetGuard、TraceRecord 等自动生效）。

**配置项**（`config.yaml` → `context` 段）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_context_tokens` | 128000 | 上下文窗口上限 |
| `compression_threshold` | 0.5 | 触发压缩的阈值比例 |
| `protected_head` | 3 | 保护的头部消息组数 |
| `protected_tail_tokens` | 20000 | 保护的尾部 token 数 |
| `min_saving` | 0.1 | 反抖动最小节省比例 |

**待后续优化**：

- 压缩状态持久化与恢复（resume 时恢复 `_last_compressed_tokens`）
- 压缩与 branch/rewind 的交互（摘要是否随 branch 隔离）
- 更精确的 token 计算（接入 tokenizer 替代字符估算）

### 8.3 A2A 多 Agent 协议

**范围**：

- Agent 之间的交互协议定义（A2A Request / Response）
- Agent 能力声明与发现机制
- A2A 作为 tool/action adapter 接入 Agent 生命周期的方式
- 安全与权限控制（一个 Agent 能对另一个 Agent 做什么）
- Agent 之间的上下文隔离（不共享 RunContext、不共享 memory）
- 异步交互模式（长时间任务）

**与核心架构的接入点**：

- 可作为一种工具接入：tool_call → a2a.call_agent → 目标 Agent 独立 AgentRun → 返回结果
- 也可作为独立 Action adapter

**依赖**：依赖工具调用通路（第三步）和基础工具规范已稳定

### 8.4 Step 插件生态

**范围**：

- 外部插件注册新 step 的机制
- 插件发现与加载（文件系统 / Python entry_points / 配置声明）
- 插件版本兼容性
- 插件安全边界（插件能访问什么、不能做什么）
- StepRegistry 配置增强：insert_before / insert_after / depends_on
- 配置 schema 校验

**与核心架构的接入点**：

- StepRegistry.register 扩展为支持外部来源
- 配置文件扩展 plugins 声明

**依赖**：依赖核心架构（第一步）稳定且经过实际使用验证

### 8.5 工具并行调度

**范围**：

- ToolSpec 增加 parallel_safe 标记
- 按安全分组并发执行策略
- 并行工具的结果收集与排序（保证确定性）
- 并行执行的 checkpoint 记录方式
- 失败处理：部分工具失败时的策略（继续 / 全部取消）
- 对 ToolPlan 的影响

**与核心架构的接入点**：

- tool_plan.build_serial → tool_plan.build（支持 serial + parallel 分组）
- tools.dispatch_serial → tools.dispatch（支持并行组内并发）

**依赖**：依赖工具调用通路（第三步）稳定

### 8.6 复杂事务与恢复修复策略

**范围**：

- message.commit_user + checkpoint.create_user_snapshot 的事务一致性保证
- 工具执行中断后的安全恢复策略（哪些工具可重试、哪些不可）
- orphan message 检测与修复（有 message 无 checkpoint 的情况）
- run interrupted 后的续跑策略（自动续跑 vs 用户确认）
- 数据一致性校验工具
- 存储层事务支持（SQLite WAL / 应用层补偿）

**与核心架构的接入点**：

- before_agent 的 commit + checkpoint 事务化
- AgentRunner 异常处理增强
- 新增修复/诊断工具

**依赖**：依赖持久化时间线（第四步）和 Resume/Rewind（第五步）已完成

## 子主题间依赖关系

```
8.1 持久化记忆 ──── 无前置依赖
8.2 上下文压缩 ──── 已完成 ✓
8.3 A2A 协议 ────── 依赖第三步（工具通路稳定）
8.4 Step 插件 ───── 依赖第一步（核心架构经过验证）
8.5 工具并行 ────── 依赖第三步（工具通路稳定）
8.6 事务恢复 ────── 依赖第四步 + 第五步
```

建议推进顺序（按优先级）：

1. 8.1 持久化记忆（对用户体验影响最大）
2. 8.2 上下文压缩（长对话必需）
3. 8.6 事务恢复（数据可靠性）
4. 8.5 工具并行（性能优化）
5. 8.3 A2A 协议（新能力扩展）
6. 8.4 Step 插件（生态建设）

## Todo List

| # | 任务 | 状态 |
|---|------|------|
| 8.1 | 持久化记忆管理机制 — 设计讨论 | pending |
| 8.2 | 持久化记忆管理机制 — 实施 | pending |
| 8.3 | 上下文压缩策略 — 设计讨论 | done |
| 8.4 | 上下文压缩策略 — 实施 | done |
| 8.5 | 复杂事务与恢复修复策略 — 设计讨论 | pending |
| 8.6 | 复杂事务与恢复修复策略 — 实施 | pending |
| 8.7 | 工具并行调度 — 设计讨论 | pending |
| 8.8 | 工具并行调度 — 实施 | pending |
| 8.9 | A2A 多 Agent 协议 — 设计讨论 | pending |
| 8.10 | A2A 多 Agent 协议 — 实施 | pending |
| 8.11 | Step 插件生态 — 设计讨论 | pending |
| 8.12 | Step 插件生态 — 实施 | pending |

## 交付与验收标准

每个子主题独立验收，启动时在各自的设计/实施文档中定义具体标准。整体完成标准：

- [ ] 每个子主题有独立的设计文档，经讨论确认后才进入实施
- [ ] 每个子主题的实施与第一版核心架构兼容，不破坏已有生命周期
- [ ] 新增能力通过 Step / Middleware / Action adapter 接入，不修改 AgentRunner 主流程
- [ ] 各子主题的依赖关系被正确遵守
- [ ] 所有测试通过
