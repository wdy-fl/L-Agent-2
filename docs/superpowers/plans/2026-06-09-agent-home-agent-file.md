# Agent Home Agent File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace local `agent.guidance_file` loading with `agent.agent_file_path`, loaded from Agent Home workspace during `base_context.load_static_parts`.

**Architecture:** `Settings` exposes `agent.agent_file_path` as the configured Agent Home logical path. `factory.py` passes that path to `BaseContextLoadStaticParts`, and the step reads the file from `ctx.home_client.workspace_get_text()` during the `before_agent` phase. Inline `guidance=` remains supported for existing tests and direct construction, but production config no longer reads local guidance files.

**Tech Stack:** Python dataclasses, pytest, existing AgentRunner lifecycle, Agent Home client workspace API.

---

## File Structure

- Modify `agent/config/settings.py`
  - Rename `AgentSettings.guidance_file` to `agent_file_path`.
  - Remove `Settings.resolve_file()` because production guidance no longer reads local files.
- Modify `agent/core/factory.py`
  - Pass `settings.agent.agent_file_path` into `BaseContextLoadStaticParts`.
  - Remove the local file read from runner assembly.
- Modify `agent/steps/before_agent.py`
  - Extend `BaseContextLoadStaticParts` with `agent_file_path`.
  - Load Agent Home text in `run()` and raise `RuntimeError` on missing client or read failure.
- Modify `tests/test_settings.py`
  - Add config parsing coverage for `agent.agent_file_path`.
- Create `tests/test_before_agent.py`
  - Add focused unit tests for `BaseContextLoadStaticParts` Agent Home loading behavior.
- Modify `tests/test_model_call_pipeline.py`
  - Keep existing test helper behavior valid by continuing to pass inline `guidance=`.
- Modify `tests/test_tool_dispatcher.py`
  - Keep existing test helper behavior valid by continuing to pass inline `guidance=`.
- Modify `config.yaml.example`
  - Replace `guidance_file` with `agent_file_path`.
- Modify `README.md`
  - Replace the config example with `agent_file_path`.

---

## Task Summary

1. Add failing settings tests for `agent_file_path` and update `AgentSettings`.
2. Add focused before-agent tests for Agent Home loading and implement `BaseContextLoadStaticParts` loading.
3. Wire `agent_file_path` through production factory.
4. Update docs and example config.
5. Run full verification.

---

## Self-Review

- Spec coverage: The plan covers config rename, removal of local file loading, Agent Home loading during `base_context.load_static_parts`, immediate failure on missing client/read errors, docs, example config, and tests.
- Placeholder scan: The plan contains no TBD/TODO placeholders and includes concrete code blocks, commands, and expected outcomes.
- Type consistency: The plan consistently uses `agent_file_path`, `workspace_get_text(path)`, `BaseContextLoadStaticParts(..., agent_file_path=...)`, and `settings.agent.agent_file_path`.
