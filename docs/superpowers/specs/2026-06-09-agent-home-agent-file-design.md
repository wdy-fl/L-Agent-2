# Agent Home AGENT.md Loading Design

## Goal

Replace the local `agent.guidance_file` configuration with `agent.agent_file_path`, a logical path inside the Agent Home workspace. During the `before_agent` phase, the `base_context.load_static_parts` step loads this file from Agent Home and uses its content as `BaseModelContext.guidance`.

## Configuration

The `agent` config section changes from:

```yaml
agent:
  guidance_file: ""
```

to:

```yaml
agent:
  agent_file_path: ""
```

Example:

```yaml
agent:
  agent_file_path: "/AGENT.md"
```

`guidance_file` is removed rather than kept as a fallback. If users still configure `guidance_file`, it will not be read.

## Architecture

`BaseContextLoadStaticParts` remains the owner of constructing `ctx.base_model_context`, but it no longer receives preloaded local guidance text from `factory.py`. Instead, it receives an optional `agent_file_path` string.

When `BaseContextLoadStaticParts.run(ctx)` executes:

1. It initializes `BaseModelContext` with the configured model settings and any static workspace context.
2. If `agent_file_path` is empty, it leaves `guidance` empty.
3. If `agent_file_path` is non-empty, it requires `ctx.home_client` to provide `workspace_get_text(path)`.
4. It loads the file content from Agent Home with `ctx.home_client.workspace_get_text(agent_file_path)`.
5. It stores the stripped file content in `ctx.base_model_context.guidance`.

This keeps Agent Home workspace access inside the `before_agent` lifecycle, matching the runtime context rather than loading the file once during runner construction.

## Data Flow

```text
workspace/config.yaml or ~/.l-agent/config.yaml
        ↓
agent.agent_file_path = "/AGENT.md"
        ↓
build_runner registers BaseContextLoadStaticParts(agent_file_path="/AGENT.md")
        ↓
before_agent runs base_context.load_static_parts
        ↓
ctx.home_client.workspace_get_text("/AGENT.md")
        ↓
ctx.base_model_context.guidance = AGENT.md content
```

## Error Handling

If `agent_file_path` is configured but the file cannot be loaded, the run fails immediately with a clear `RuntimeError` that includes the path. Failure cases include:

- `ctx.home_client` is missing.
- `ctx.home_client` does not expose `workspace_get_text`.
- Agent Home returns an error, including file-not-found.
- Network or transport errors occur while reading the object.

The error must not silently downgrade to empty guidance, because running without the configured AGENT.md would hide configuration mistakes.

## Files to Update

- `agent/config/settings.py`
  - Rename `AgentSettings.guidance_file` to `agent_file_path`.
  - Remove `Settings.resolve_file()` if no references remain.
- `agent/core/factory.py`
  - Stop calling `settings.resolve_file(settings.agent.guidance_file)`.
  - Register `BaseContextLoadStaticParts(agent_file_path=settings.agent.agent_file_path, model_config=model_config)`.
- `agent/steps/before_agent.py`
  - Update `BaseContextLoadStaticParts` to load `agent_file_path` from `ctx.home_client.workspace_get_text()` during `run()`.
- `config.yaml.example`
  - Replace `guidance_file` with `agent_file_path`.
- `README.md`
  - Update the configuration example.
- Tests using `BaseContextLoadStaticParts`
  - Keep direct `guidance=` support for tests that want inline guidance, or update them to use a fake home client where they test Agent Home loading.

## Testing

Add or adjust tests for these behaviors:

1. Empty `agent_file_path` keeps guidance empty unless direct `guidance` is explicitly provided by a test.
2. Non-empty `agent_file_path` loads content from a fake `home_client.workspace_get_text`.
3. Non-empty `agent_file_path` without `ctx.home_client` raises `RuntimeError`.
4. `workspace_get_text` exceptions are wrapped in `RuntimeError` with the configured path included.
5. Config parsing accepts `agent.agent_file_path`.

Run the relevant pytest suite after implementation.
