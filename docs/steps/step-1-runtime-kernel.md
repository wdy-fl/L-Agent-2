# 第一步：运行内核骨架

## 环节定位

L-Agent 实施计划的第一步。搭建 Agent 运行的最小骨架：固定八段生命周期、Step/Middleware 扩展机制、AgentRunner 流程推进器。本步不涉及真实 LLM 调用、工具执行或持久化，只验证生命周期流转逻辑的正确性。

## 注意事项

- AgentRunner 只做流程控制，不包含任何具体业务逻辑
- 生命周期八段固定，不提供配置增删阶段的能力
- RunContext 字段先定义占位，后续步骤逐步填充语义
- Middleware 只包裹 model_call / tool_call 两个 Action，不用于普通 Step
- checkpoint 记录先留接口（方法签名），不接存储实现
- Step 第一版不做复杂 depends_on / config_schema / plugin metadata

## 详细内容

### 1.1 生命周期定义

- `HookPhase` 枚举：before_agent / before_model / after_model / before_tool / after_tool / after_agent
- `ActionName` 枚举：model_call / tool_call
- 阶段分类标识：
  - run 级阶段：before_agent / after_agent（每次 AgentRun 只执行一次）
  - iteration 级阶段：before_model / after_model / before_tool / after_tool（每轮 ReAct 都可能执行）
- before_tool / tool_call / after_tool 只有模型返回 tool_calls 时才执行

### 1.2 RunContext

全局可变运行上下文，贯穿一次 AgentRun。字段定义：

- 基础字段：session / branch / run / input / iterations / errors / runtime state
- 模型相关占位：base_model_context / current_model_request / current_model_response
- 工具相关占位：current_tool_plan / current_tool_results
- 结果相关：final_result / has_tool_calls

RunContext 是一次 AgentRun 的黑板，不是整个 Session 的上下文。

### 1.3 Step 基类与 Registry

Step 是 Hook Phase 内部的可插拔能力模块。

Step 基类采用类接口式：

```python
class Step:
    name: str
    phase: HookPhase

    def run(self, ctx: RunContext) -> None:
        ...
```

StepRegistry 负责：

- 注册 Step
- 按 phase 收集 Step
- 按配置启用/禁用 Step
- 按配置调整 Step 顺序
- 为 AgentRunner 提供 phase → steps 映射

配置第一版支持 enabled、参数和数值优先级（priority，数值越小越先执行）。

### 1.4 Middleware 基类与 Chain

Middleware 只包裹 Action（model_call / tool_call），不用于普通 Step。

Middleware 采用轻量接口：

```python
class Middleware:
    name: str
    target: ActionName

    def __call__(self, ctx: RunContext, next_call: Callable) -> Any:
        ...
```

MiddlewareChain 按洋葱模型组装 middleware 列表，包裹 action 执行：

```
middleware_1(
  middleware_2(
    middleware_3(
      action
    )
  )
)
```

配置只控制 Middleware 的启停和参数，不改变 Action 本身。

### 1.5 AgentRunner

AgentRunner 是一次 AgentRun 的流程推进器。

职责：

- 创建并持有 RunContext
- 执行 before_agent
- 驱动 ReAct loop
- 执行 before_model / model_call / after_model
- 有 tool_calls 时执行 before_tool / tool_call / after_tool
- 执行 after_agent
- 自动记录 action 边界 runtime checkpoint
- 根据 ctx.final_result / tool_calls / errors 判断流程走向

AgentRunner 不负责具体业务：

- 不直接做 memory
- 不直接做 tool parsing
- 不直接做 compression
- 不直接做 persistence details

这些都由 Step、Action、Middleware 或 Store 完成。

完整执行结构：

```
AgentRun
├── before_agent
├── while not finished:
│   ├── before_model
│   ├── model_call
│   ├── after_model
│   ├── if has_tool_calls:
│   │   ├── before_tool
│   │   ├── tool_call
│   │   └── after_tool
│   └── else:
│       └── break (final_result set)
└── after_agent
```

循环退出条件：

- ctx.final_result 被设置（模型无 tool_calls，产生最终回复）
- 错误发生
- 中断信号

Action 执行时由 AgentRunner 自动记录 runtime checkpoint（本步先留接口，不接存储）：

- model_call_started / model_call_completed / model_call_failed
- tool_call_started / tool_call_completed / tool_call_failed

## Todo List

| # | 任务 | 状态 |
|---|------|------|
| 1.1 | 定义 `HookPhase` 枚举（六个 phase + run/iteration 级分类） | done |
| 1.2 | 定义 `ActionName` 枚举（model_call / tool_call） | done |
| 1.3 | 定义 `RunContext` 数据结构（基础字段 + 模型/工具/结果占位） | done |
| 1.4 | 实现 `Step` 基类（name / phase / run(ctx)） | done |
| 1.5 | 实现 `StepRegistry`（register / get_steps / configure 启停与参数） | done |
| 1.6 | 实现 `Middleware` 基类（name / target / `__call__(ctx, next_call)`） | done |
| 1.7 | 实现 `MiddlewareChain`（洋葱模型组装与执行） | done |
| 1.8 | 实现 `AgentRunner` 主流程（before_agent → ReAct loop → after_agent） | done |
| 1.9 | 实现 AgentRunner 的 ReAct 循环逻辑（退出条件判断） | done |
| 1.10 | AgentRunner 自动记录 action 边界 checkpoint（接口占位） | done |
| 1.11 | 编写单元测试：验证 phase 执行顺序正确 | done |
| 1.12 | 编写单元测试：验证 Middleware 洋葱模型执行 | done |
| 1.13 | 编写单元测试：验证 has_tool_calls 分支逻辑 | done |
| 1.14 | 编写单元测试：验证异常/中断时进入 after_agent | done |

## 交付与验收标准

- [x] 注册空 step，AgentRunner 能按正确顺序调用各 phase 的 steps
- [x] Action + Middleware 链能正确执行（middleware 按洋葱模型包裹 action）
- [x] has_tool_calls=False 时跳过工具段（before_tool / tool_call / after_tool），退出 ReAct 循环
- [x] has_tool_calls=True 时进入工具段，完成后回到 before_model 继续循环
- [x] 异常/中断时 AgentRunner 能正确退出并进入 after_agent
- [x] StepRegistry 的 configure 能启停 step
- [x] 所有测试通过（14 tests passed）
