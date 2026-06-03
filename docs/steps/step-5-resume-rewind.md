# 第五步：Resume 与 Rewind

## 环节定位

L-Agent 实施计划的第五步。基于第四步的持久化时间线，实现 resume（恢复最新完整运行结果继续对话）和 rewind（从用户输入 checkpoint fork 新 branch）两大会话恢复能力。

## 注意事项

- resume 恢复的是 active branch 最新 run_completed 后的完整上下文，不重跑上一轮
- rewind 不删除旧历史，而是从 user_message_committed checkpoint 创建新 branch
- 新 branch 通过 base_message_cursor 实现结构共享，不复制 parent branch 的消息
- 恢复上下文时：parent branch 中 cursor 之前的消息 + 新 branch 自己的消息
- 如果上次 run interrupted，resume 恢复到最后一个 completed run，并提示中断信息
- 创建 session 时自动创建默认 branch（相当于 main）
- rewind 后旧 branch 保留不变，可查看但不再 active

## 详细内容

### 5.1 Branch 管理

- 创建 session 时自动创建默认 branch（status=active）
- session.active_branch_id 指向当前工作的 branch
- branch.resume_head 指向最新完整运行结果对应的 checkpoint

### 5.2 before_agent step：branch.resolve_active

加载 session 的 active branch，判断当前状态：

- 新 session：使用刚创建的默认 branch
- resume 进入的 session：active branch 已有历史，正常追加
- rewind 后的新 branch：从 fork point 开始追加

将 branch 信息写入 ctx.branch。

### 5.3 after_agent step：branch.update_resume_head

仅当 run completed 时：

- 更新 branch.resume_head 指向本次 run_completed checkpoint
- 如果 run failed / interrupted，不更新 resume_head

### 5.4 Resume 语义实现

```
resume(session_id):
  → 找到 session 的 active branch
  → 找到 branch 的 resume_head（最新 run_completed checkpoint）
  → 根据 checkpoint.message_cursor 恢复所有 messages
  → 将 messages 加载到 RunContext
  → 等待用户新输入，开始新 AgentRun
```

resume 恢复的内容：

- 该 branch 上所有已提交的 messages（user / assistant / tool）
- 包括压缩后的摘要（如有）
- 不包括 interrupted run 的未完成内容

如果上次 run interrupted：

- resume 恢复到最后一个 completed run 的状态
- 向用户提示：上次运行中断在某个阶段

### 5.5 Rewind 语义实现

```
rewind(checkpoint_id):
  → 找到 checkpoint（必须是 user_message_committed 类型）
  → 创建新 branch:
      parent_branch_id = checkpoint.branch_id
      fork_checkpoint_id = checkpoint.id
      base_message_cursor = checkpoint.message_cursor
  → 切换 session.active_branch_id = new_branch.id
  → 恢复上下文：parent branch 中 message_cursor 之前的消息
  → 等待用户新输入（或重新运行该 user message）
```

Rewind 后的上下文：

- 包含该 user message
- 不包含它之后的 assistant/tool 结果
- 后续新消息写入新 branch

创建新 branch 不会：

- 删除旧 branch 消息
- 复制旧消息
- 自动重跑旧工具
- 修改 checkpoint 之前的历史

### 5.6 messages.collect_visible 适配 branch 结构共享

当前 branch 可能有 parent：

```
收集 visible messages:
  if branch.parent_branch_id:
    parent_messages = store.get_messages(parent_branch_id, up_to=base_message_cursor)
  else:
    parent_messages = []
  own_messages = store.get_messages(branch_id)
  return parent_messages + own_messages
```

这样实现结构共享：新 branch 不复制旧消息，只通过游标引用。

### 5.7 Interrupted run 处理

resume 时如果发现最新 run 是 interrupted：

- 不恢复该 interrupted run 的中间状态
- 恢复到上一个 completed run 的 resume_head
- 向用户提示中断信息（中断阶段、pending tool_calls 等）

## Todo List

| # | 任务 | 状态 |
|---|------|------|
| 5.1 | 实现 session 创建时自动创建默认 branch | done |
| 5.2 | 实现 before_agent step `branch.resolve_active`（加载 active branch） | done |
| 5.3 | 实现 after_agent step `branch.update_resume_head`（completed 时更新） | done |
| 5.4 | 实现 resume 逻辑：找到 resume_head → 恢复 messages → 加载到 RunContext | done |
| 5.5 | 实现 rewind 逻辑：校验 checkpoint → 创建新 branch → 切换 active | done |
| 5.6 | 适配 messages.collect_visible 支持 branch 结构共享（parent + own） | done |
| 5.7 | 处理 interrupted run 的 resume：恢复到上一个 completed，提示中断 | done |
| 5.8 | 实现 rewind 后上下文正确性（包含 user message，不包含后续） | done |
| 5.9 | 编写测试：多轮对话后 resume 恢复完整上下文 | done |
| 5.10 | 编写测试：resume 后模型能看到所有历史 messages | done |
| 5.11 | 编写测试：rewind 到某条用户输入，新 branch 上下文正确 | done |
| 5.12 | 编写测试：旧 branch 历史保留不变 | done |
| 5.13 | 编写测试：新 branch 后续对话正常追加 | done |
| 5.14 | 编写测试：interrupted run 时 resume 恢复到 completed 状态 | done |

## 交付与验收标准

- [x] 一次 session 多轮对话后退出，resume 能恢复完整上下文继续
- [x] resume 后模型能看到之前所有对话历史（messages 完整）
- [x] rewind 到某条用户输入，新 branch 上下文正确（包含该 user message，不包含之后的 assistant/tool）
- [x] rewind 后旧 branch 历史保留不变，可查看
- [x] interrupted run 时 resume 恢复到最后一个 completed 状态
- [x] 新 branch 后续对话正常追加，不影响 parent branch
- [x] branch 结构共享正确（不复制消息，通过 cursor 引用）
- [x] 所有测试通过
