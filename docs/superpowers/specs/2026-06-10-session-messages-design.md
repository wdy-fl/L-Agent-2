# Session Messages Design

## Goal

Make `ctx.messages` the single source of truth for the full session conversation context. Every model request should send this list directly. The first message is always the session system prompt, and the system prompt is created only once during the first `AgentRun` of a new session.

## Decisions

- Delete `BaseModelContext`.
- `system` prompt contains only `guidance`.
- Do not include `workspace_context` or `memory_context` in the system prompt.
- Do not add a cross-run in-memory cache yet; load from `timeline_store` each run when `ctx.messages` is empty.
- Do not keep no-store fallback behavior; all tests and production runs that use the normal lifecycle must provide a `timeline_store`, `session_id`, and `branch_id`.
- Use fail-fast behavior for all missing dependencies and persistence/load errors.

## Architecture

### `RunContext`

`RunContext` should directly hold the runtime fields needed for model requests:

- `messages`: visible conversation context sent to the model.
- `model_config`: model name, token limit, temperature, API config.
- `available_tools`: current tool schemas.
- `enhanced_input`: user input after memory augmentation.

It should no longer hold `base_model_context`.

### `ContextInitialize`

`ContextInitialize` remains the first `before_agent` step. It should:

1. Initialize `run_id`, `iterations`, `iteration_index`, and `status`.
2. Set `ctx.model_config`.
3. Require `timeline_store`, `session_id`, and `branch_id` when normal message initialization is needed.
4. If `ctx.messages` is empty, load visible history from `timeline_store` using the existing resume semantics for the current session.
5. Convert timeline `Message` records into model message dictionaries.
6. If history is still empty, load `guidance` or `agent_file_path`, create `{"role": "system", "content": guidance}`, append it to `ctx.messages`, and persist it to `timeline_store`.
7. If history is not empty, skip guidance loading entirely.

This keeps guidance loading limited to the first run of a new session.

### `MemoryPrefetch`

`MemoryPrefetch` should no longer write memory into a base model context. It should:

1. Search memory using the raw `ctx.input`.
2. Set `ctx.enhanced_input = ctx.input` when no memory is returned.
3. Set `ctx.enhanced_input` to a memory block plus the original user input when memory is returned.

Recommended enhanced input format:

```text
<memory>
- [type] content
</memory>

<user>
original user input
</user>
```

`ctx.input` remains unchanged and always represents the raw user input.

### `MessageCommitUser`

`MessageCommitUser` should:

1. Require `ctx.enhanced_input` to be available, defaulting to `ctx.input` only if the memory step explicitly set that value.
2. Append `{"role": "user", "content": ctx.enhanced_input}` to `ctx.messages`.
3. Persist the same enhanced input as a `user` timeline message.

It should not initialize `ctx.messages` by itself. System/history initialization belongs to `ContextInitialize`.

### `ToolsSnapshotAvailableTools`

`ToolsSnapshotAvailableTools` should write tool schemas directly to `ctx.available_tools`.

### `ModelRequestCompose`

`ModelRequestCompose` should compose a `ModelRequest` directly from:

- `ctx.messages`
- `ctx.available_tools`
- `ctx.model_config`

It should not prepend a synthetic system message and should not read `BaseModelContext`.

### Assistant And Tool Messages

Existing ReAct loop behavior should remain conceptually the same:

- `MessageCommitAssistant` appends assistant messages to `ctx.messages` and persists them to `timeline_store`.
- `MessageCommitToolResults` appends tool messages to `ctx.messages` and persists them to `timeline_store`.
- Assistant `tool_calls` and tool `tool_call_id` fields must be preserved so tool-call message grouping remains valid.

## Step Order

The production `before_agent` step order should be:

1. `ContextInitialize`
2. `RunCreate`
3. `MemoryPrefetch`
4. `MessageCommitUser`
5. `CheckpointCreateUserSnapshot`
6. `ToolsSnapshotAvailableTools`
7. `BudgetInitialize`

Rationale:

- `ContextInitialize` must create `run_id` before `RunCreate`.
- `RunCreate` should create the run before user messages are persisted with that run id.
- `MemoryPrefetch` must run before `MessageCommitUser` so the persisted user message uses enhanced input.
- Tool snapshot and budget initialization can remain after message preparation because they do not affect timeline message creation.

## History Loading

History loading should use the existing resume semantics rather than directly querying a branch when possible. This preserves:

- active branch selection
- parent branch history
- `resume_head` cursor behavior
- interrupted run rollback behavior

Timeline messages should map to model messages as follows:

- `system`, `user`, `assistant`: include `role` and `content`.
- assistant messages with `tool_calls`: include `tool_calls`.
- tool messages: include `role`, `tool_call_id`, and `content`.

## Error Handling

Use fail-fast behavior.

- Missing `timeline_store` raises.
- Missing `session_id` or `branch_id` raises.
- Session, branch, checkpoint, or history load failures raise.
- `agent_file_path` read failures raise.
- Memory search failures raise.
- Timeline persistence failures raise.

No fallback path should silently continue with partial context.

## Test Plan

Update tests so normal lifecycle tests always provide a store, session id, and branch id.

Required coverage:

1. New session first run inserts a persisted system message as `ctx.messages[0]`.
2. Existing session loads history and does not reload guidance.
3. `MessageCommitUser` appends and persists enhanced input.
4. `MemoryPrefetch` produces raw input when no memory exists.
5. `MemoryPrefetch` produces memory block plus raw input when memory exists.
6. `ModelRequestCompose` sends `ctx.messages` directly and uses `ctx.available_tools` and `ctx.model_config`.
7. Multi-turn runner flow sends system, previous user/assistant, and current enhanced user messages in the second turn.
8. Resume after interrupted run uses resume semantics and excludes messages after the stable resume cursor.
9. Tool-call flow preserves assistant `tool_calls` and tool `tool_call_id` in both `ctx.messages` and timeline.
10. Missing store/session/branch raises instead of falling back.

## Out Of Scope

- Cross-run in-memory message cache.
- Workspace context in system prompt.
- Memory context in system prompt.
- Silent fallback for no-store execution.
- CLI-specific history loading in `_handle_run`.
