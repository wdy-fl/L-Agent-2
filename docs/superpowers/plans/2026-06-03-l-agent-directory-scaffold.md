# L-Agent Directory Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the first L-Agent project directory scaffold using `agent/` as the Python package and `agent/core/` as the runtime kernel module.

**Architecture:** This scaffold follows the approved L-Agent design: `agent/core` owns the runtime kernel, `agent/steps` owns lifecycle Step modules, `agent/actions` and `agent/middleware` separate fixed actions from action wrappers, and `agent/timeline` owns Session / Branch / Checkpoint concepts. This task only creates directories and empty package markers; it does not implement behavior.

**Tech Stack:** Python 3 package layout, POSIX shell directory creation, Python 3 verification script.

---

## File Structure

Create the following structure under `/Users/wangdeyu/Desktop/OPC-Agent/L-Agent`:

```text
L-Agent/
├── main.py
├── pyproject.toml
├── README.md
├── config.yaml.example
├── agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── runner.py
│   │   ├── context.py
│   │   ├── lifecycle.py
│   │   └── result.py
│   ├── steps/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── before_agent.py
│   │   ├── before_model.py
│   │   ├── after_model.py
│   │   ├── before_tool.py
│   │   ├── after_tool.py
│   │   └── after_agent.py
│   ├── actions/
│   │   ├── __init__.py
│   │   ├── model_call.py
│   │   └── tool_call.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── chain.py
│   │   ├── model.py
│   │   └── tool.py
│   ├── timeline/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── store.py
│   │   ├── resume.py
│   │   └── rewind.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── dispatcher.py
│   │   └── builtin/
│   │       ├── __init__.py
│   │       ├── file_ops.py
│   │       ├── terminal.py
│   │       ├── web.py
│   │       └── think.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── types.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── interface.py
│   │   └── simple.py
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── index.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── sqlite.py
│   │   └── schema.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── interface.py
│   └── workspace/
│       ├── __init__.py
│       └── paths.py
├── workspace/
│   ├── logs/
│   ├── memory/
│   └── skills/
└── tests/
    ├── test_agent_runner.py
    ├── test_lifecycle_steps.py
    ├── test_timeline_resume.py
    ├── test_timeline_rewind.py
    ├── test_tool_dispatcher.py
    └── test_middleware.py
```

Existing files `design.md`, `docs/`, and exported discussion files must be preserved.

### Task 1: Create L-Agent directory scaffold

**Files:**
- Create: `/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/main.py`
- Create: `/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/pyproject.toml`
- Create: `/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/README.md`
- Create: `/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/config.yaml.example`
- Create: all package files listed in the File Structure section
- Create: all test placeholder files listed in the File Structure section

- [ ] **Step 1: Create package and workspace directories**

Run:

```bash
mkdir -p "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/actions" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/llm" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/memory" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/skills" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/config" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/storage" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/cli" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/workspace" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/workspace/logs" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/workspace/memory" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/workspace/skills" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests"
```

Expected: command exits with status 0.

- [ ] **Step 2: Create empty package and module files**

Run:

```bash
touch "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/main.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/pyproject.toml" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/README.md" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/config.yaml.example" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/agent.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/runner.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/context.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/lifecycle.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/core/result.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/base.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/registry.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/before_agent.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/before_model.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/after_model.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/before_tool.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/after_tool.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/steps/after_agent.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/actions/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/actions/model_call.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/actions/tool_call.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware/base.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware/chain.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware/model.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/middleware/tool.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline/models.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline/store.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline/resume.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/timeline/rewind.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/base.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/registry.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/dispatcher.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin/file_ops.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin/terminal.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin/web.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/tools/builtin/think.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/llm/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/llm/client.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/llm/types.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/memory/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/memory/interface.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/memory/simple.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/skills/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/skills/loader.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/skills/index.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/config/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/config/settings.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/storage/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/storage/sqlite.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/storage/schema.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/cli/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/cli/interface.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/workspace/__init__.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/agent/workspace/paths.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_agent_runner.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_lifecycle_steps.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_timeline_resume.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_timeline_rewind.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_tool_dispatcher.py" "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent/tests/test_middleware.py"
```

Expected: command exits with status 0.

- [ ] **Step 3: Verify scaffold exists with Python 3**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
root = Path('/Users/wangdeyu/Desktop/OPC-Agent/L-Agent')
required = [
    'main.py', 'pyproject.toml', 'README.md', 'config.yaml.example',
    'agent/__init__.py', 'agent/core/runner.py', 'agent/core/context.py', 'agent/core/lifecycle.py',
    'agent/steps/base.py', 'agent/steps/registry.py', 'agent/actions/model_call.py',
    'agent/middleware/chain.py', 'agent/timeline/models.py', 'agent/tools/dispatcher.py',
    'agent/tools/builtin/file_ops.py', 'agent/llm/client.py', 'agent/memory/interface.py',
    'agent/skills/loader.py', 'agent/config/settings.py', 'agent/storage/sqlite.py',
    'agent/cli/interface.py', 'agent/workspace/paths.py', 'workspace/logs', 'workspace/memory',
    'workspace/skills', 'tests/test_agent_runner.py', 'tests/test_middleware.py',
]
missing = [path for path in required if not (root / path).exists()]
if missing:
    raise SystemExit('Missing scaffold paths: ' + ', '.join(missing))
print('L-Agent scaffold verified')
PY
```

Expected output:

```text
L-Agent scaffold verified
```

- [ ] **Step 4: Inspect final tree**

Run:

```bash
find "/Users/wangdeyu/Desktop/OPC-Agent/L-Agent" -maxdepth 3 -print
```

Expected: output includes `agent/core`, `agent/steps`, `agent/actions`, `agent/middleware`, `agent/timeline`, `agent/tools`, `agent/llm`, `agent/memory`, `agent/skills`, `agent/config`, `agent/storage`, `agent/cli`, `agent/workspace`, `workspace`, and `tests`.

## Self-Review

- Spec coverage: The plan creates the approved directory scaffold with top-level Python package `agent/` and runtime kernel directory `agent/core/`.
- Placeholder scan: No TBD, TODO, or unspecified implementation steps are present.
- Type consistency: No runtime types or behavior are implemented in this scaffold; file and directory names are consistent across structure, commands, and verification.
