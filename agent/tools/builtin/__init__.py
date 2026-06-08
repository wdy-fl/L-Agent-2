"""Built-in tools registry and approval configuration."""

from typing import Protocol

from agent.tools.builtin.file_ops import AgentHomeWorkspace, create_agent_home_file_tools
from agent.tools.builtin.terminal import AgentHomeCommandRunner, create_agent_home_terminal_tool
from agent.tools.builtin.think import think_tool
from agent.tools.builtin.web import web_fetch_tool, web_search_tool
from agent.tools.registry import ToolRegistry

AUTO_APPROVE_TOOLS = frozenset({
    "think",
    "read_file",
    "list_directory",
    "search_file",
    "web_search",
    "web_fetch",
})

ALWAYS_CONFIRM_TOOLS = frozenset({
    "terminal",
    "write_file",
})


class AgentHomeToolClient(AgentHomeWorkspace, AgentHomeCommandRunner, Protocol):
    pass


def create_builtin_registry(home_client: AgentHomeToolClient | None = None) -> ToolRegistry:
    if home_client is None:
        raise RuntimeError("Agent Home client is required to create the built-in tool registry.")

    registry = ToolRegistry()
    tools = [
        think_tool,
        *create_agent_home_file_tools(home_client),
        create_agent_home_terminal_tool(home_client),
        web_search_tool,
        web_fetch_tool,
    ]
    for tool in tools:
        registry.register(tool)
    return registry
