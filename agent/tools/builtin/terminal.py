"""Built-in terminal tool: execute shell commands with timeout."""

from __future__ import annotations

import subprocess
from typing import Any, Protocol

from agent.tools.base import ToolSpec


class AgentHomeCommandRunner(Protocol):
    def workspace_run_command(self, command: str, timeout_seconds: int = 120, env: dict[str, str] | None = None) -> dict[str, Any]: ...


def _terminal_handler(command: str, timeout: int = 120, cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        parts.append(f"[exit_code: {result.returncode}]")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command timed out after {timeout}s: {command}")


terminal_tool = ToolSpec(
    name="terminal",
    description="Execute a shell command and return stdout, stderr, and exit code. Use for running builds, tests, git commands, etc.",
    parameters_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default: 120."},
            "cwd": {"type": "string", "description": "Working directory for the command."},
        },
        "required": ["command"],
    },
    handler=_terminal_handler,
)


def create_agent_home_terminal_tool(home_client: AgentHomeCommandRunner) -> ToolSpec:
    workspace_terminal_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute inside the Agent-Home workspace sandbox."},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default: 120."},
        },
        "required": ["command"],
    }

    def terminal(command: str, timeout: int = 120) -> str:
        result = home_client.workspace_run_command(command, timeout_seconds=timeout)
        parts: list[str] = []
        if result.get("stdout"):
            parts.append(result["stdout"])
        if result.get("stderr"):
            parts.append(f"[stderr]\n{result['stderr']}")
        changed_paths = result.get("changed_paths") or []
        if changed_paths:
            parts.append(f"[changed_paths] {' '.join(str(path) for path in changed_paths)}")
        parts.append(f"[exit_code: {result.get('exit_code', 0)}]")
        return "\n".join(parts)

    return ToolSpec(
        name=terminal_tool.name,
        description="Execute a shell command inside the Agent-Home workspace sandbox and return stdout, stderr, changed paths, and exit code.",
        parameters_schema=workspace_terminal_schema,
        handler=terminal,
    )
