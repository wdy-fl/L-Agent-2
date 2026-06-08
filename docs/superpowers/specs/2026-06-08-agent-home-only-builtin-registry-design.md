# Agent Home Only Built-in Registry Design

## Context

`agent/tools/builtin/__init__.py` currently builds a `ToolRegistry` in two modes:

- Without `home_client`, it registers local file and terminal tools.
- With `home_client`, it registers Agent Home workspace file tools and Agent Home sandbox terminal tools.

The requested change is to remove the local registry mode. Built-in file and terminal tools should only be available through Agent Home. If `home_client` is missing, registry creation should fail with `RuntimeError`.

## Goals

- Remove the local-tool aggregation path from the built-in registry module.
- Ensure `create_builtin_registry` only registers Agent Home-backed file and terminal tools.
- Fail clearly with `RuntimeError` when `home_client` is not provided.
- Preserve existing public tool names so model/tool callers still see `read_file`, `write_file`, `list_directory`, `search_file`, and `terminal`.
- Update tests that assumed local-tool registration without `home_client`.

## Non-goals

- Do not remove local tool implementations from `file_ops.py` or `terminal.py` in this change unless they are unused by the registry. They may still be useful for lower-level tests or future reuse.
- Do not change approval policy constants unless imports or tests require it.
- Do not change Agent Home workspace client behavior.

## Proposed Architecture

`agent/tools/builtin/__init__.py` becomes the Agent Home-only registry entrypoint.

It should import only what it needs to assemble Agent Home-backed tools:

- `AgentHomeWorkspace`
- `create_agent_home_file_tools`
- `AgentHomeCommandRunner`
- `create_agent_home_terminal_tool`
- `think_tool`
- `web_search_tool`
- `web_fetch_tool`
- `ToolRegistry`

The module should no longer expose an `ALL_BUILTIN_TOOLS` list containing local tool objects.

`create_builtin_registry` should keep a defensive runtime check:

```python
def create_builtin_registry(home_client: AgentHomeToolClient | None = None) -> ToolRegistry:
    if home_client is None:
        raise RuntimeError("Agent Home client is required to create the built-in tool registry.")
    ...
```

After the check, it should register only:

1. `think_tool`
2. all tools returned by `create_agent_home_file_tools(home_client)`
3. `create_agent_home_terminal_tool(home_client)`
4. `web_search_tool`
5. `web_fetch_tool`

## Data Flow

1. Application setup obtains or constructs an Agent Home client.
2. `agent/core/factory.py` calls `create_builtin_registry(home_client=home_client)`.
3. The registry exposes the same tool names as before.
4. File operations flow through `home_client.workspace_get_text`, `home_client.workspace_put`, and `home_client.workspace_list`.
5. Terminal operations flow through `home_client.workspace_run_command`.
6. If application setup passes `None`, `create_builtin_registry` raises `RuntimeError` before any registry is returned.

## Error Handling

- Missing `home_client` raises `RuntimeError` with a message that clearly identifies Agent Home client configuration as required.
- Existing Agent Home file and terminal tool errors remain unchanged.
- Invalid regex handling in Agent Home search remains unchanged.

## Test Strategy

Update or add tests to cover:

- `create_builtin_registry(home_client=None)` raises `RuntimeError`.
- A fake Agent Home client produces a registry with expected schemas/tool names.
- `read_file`, `write_file`, `list_directory`, `search_file`, and `terminal` call fake Agent Home workspace methods.
- Tests that previously called `create_builtin_registry()` without a client should either move to direct local tool tests or use a fake Agent Home client, depending on what behavior they are asserting.

## Implementation Notes

Search results show current call sites:

- `agent/core/factory.py` already passes `home_client=home_client`.
- `tests/test_agent_home_tools.py` already passes a fake Agent Home client.
- `tests/test_builtin_tools.py` has no-argument registry tests and will need updates.

The implementation should preserve web and think tools because they are not local file/terminal workspace implementations.

## Self-review

- No placeholder requirements remain.
- Scope is limited to built-in registry behavior and tests.
- Runtime failure mode is explicit: `RuntimeError` on missing `home_client`.
- Tool names remain stable while implementations are Agent Home-backed.
