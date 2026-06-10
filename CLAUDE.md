# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

```bash
pip install -e .                        # Install in editable mode (Python >= 3.11)
pip install pytest pytest-asyncio       # Install test dependencies
pytest                                  # Run all tests
pytest tests/test_agent_runner.py       # Run a single test file
pytest tests/test_agent_runner.py::TestToolCallsBranching::test_has_tool_calls_true_enters_tool_phase  # Run a single test
```

## Architecture

L-Agent-2 is a CLI-based AI Coding Agent using the ReAct (Reason + Act) loop pattern. The entry point is `l-agent` (`agent.cli.app:app`, a Typer CLI).

### Lifecycle phases

`AgentRunner.run()` (an async generator yielding `AgentEvent`) drives a fixed eight-phase lifecycle through a `StepRegistry`:

1. `before_agent` — initialize context, load memory, snapshot tools, create run
2. `before_model` — increment iteration counter, compress context if needed, compose `ModelRequest`
3. `model_call` — wrapped by `MiddlewareChain` (budget guard → trace → actual LLM call)
4. `after_model` — capture response, commit assistant message to timeline, update token usage, detect final answer or tool calls
5. `before_tool` — extract tool calls from response, parse args, validate schema, resolve tool specs, build serial execution plan
6. `tool_call` — wrapped by middleware (approval guard → audit → result truncation), dispatches via `ToolDispatcher`
7. `after_tool` — capture tool results, commit tool messages to timeline
8. `after_agent` — finalize run, optionally extract memory

The loop repeats from phase 2 until the model produces a final answer without tool calls, budget is exhausted, or the user interrupts.

### Key concepts

- **`RunContext`** (`agent/core/context.py`): A mutable dataclass blackboard carrying all state for a single agent run — messages, model request/response, tool plan/results, budget, timeline references. Passed through every Step and Middleware.
- **`Step`** (`agent/steps/base.py`): Abstract base with `name`, `phase` (HookPhase), and `run(ctx)` method. Registered into `StepRegistry` which sorts by priority within each phase.
- **`Middleware`** (`agent/middleware/base.py`): Wraps `model_call` or `tool_call` actions in an onion pattern. Each middleware has a `target` (`ActionName`) and a `__call__(ctx, next_call)` method.
- **`MiddlewareChain`**: Chains middleware for a given target action so each middleware can intercept before/after the core action.
- **`AgentRunner`** (`agent/core/runner.py`): Orchestrates phases, middleware, and actions. `run()` yields typed `AgentEvent` dataclasses (Token, ModelDone, ToolStart, ToolDone, ApprovalRequest, RunDone, RunError) consumed by the CLI renderer.
- **`Factory`** (`agent/core/factory.py`): `build_runner()` assembles settings, LLM client, tool registry, dispatcher, all step instances, all middleware instances, and wires up the `AgentRunner`.

### Timeline / persistence

The project has two `TimelineStore` implementations (abstract interface at `agent/timeline/store.py`):

- **`SQLiteTimelineStore`** (`agent/storage/sqlite.py`): Local SQLite with tables for sessions, branches, agent_runs, messages, checkpoints.
- **`AgentHomeClient`** (`agent/home/client.py`): HTTP client implementing the same interface against a remote Agent-Home server. Also provides workspace operations (file read/write, command execution) and memory operations.

**Timeline model** (`agent/timeline/models.py`): `Session` → `Branch` (forking for rewinds) → `AgentRun` → `Message` (sequence-numbered, per-branch). `Checkpoint` stores a message cursor for rewind points.

- `resume(store, session_id)`: Loads the active branch's messages (recursively following parent branches for rewind ancestry).
- `rewind(store, session_id, checkpoint_id)`: Creates a new branch forked at the checkpoint, sets it as session's active branch.
- `create_session_with_default_branch()`: Creates a session with a single initial branch.

### Context compression

`ContextCompressor` (`agent/context/compressor.py`) handles long conversations. When token count exceeds `threshold * context_window`, triggers LLM-based summarization:
1. Trims tool result content in the middle segment
2. Extracts any previous summary blocks
3. Calls LLM to generate a structured Chinese-language summary (task, completed, in-progress, decisions, pending issues, files, remaining work)
4. Wraps summary in `<context-summary>` tags in an assistant message
5. Falls back to iterative compression with per-call saving check (avoids re-compressing when saving is too small)

### Tools

All built-in tools are backed by the AgentHome HTTP API. Defined as `ToolSpec` dataclasses (`agent/tools/base.py`) with name, description, JSON schema, and handler. Registered in `ToolRegistry`. Built-in tools: `think`, `read_file`, `write_file`, `list_directory`, `search_file`, `terminal`, `web_search`, `web_fetch`.

- `AUTO_APPROVE_TOOLS`: think, read_file, list_directory, search_file, web_search, web_fetch
- `ALWAYS_CONFIRM_TOOLS`: terminal, write_file

### Config

YAML config loaded from `workspace/config.yaml` or `~/.l-agent/config.yaml`. Sections: `llm`, `budget`, `context`, `agent`, `agent_home`. See `config.yaml.example`.

### CLI

`CLISession` (`agent/cli/app.py`) wraps `AgentRunner.run()` with a prompt_toolkit input loop + Rich rendering. Supports slash commands (`/new`, `/list`, `/resume`, `/rewind`, `/status`) dispatched by `CommandDispatcher` (`agent/cli/commands.py`).
