"""Built-in tools registry and approval configuration."""

from typing import Protocol

from agent.tools.builtin.file_ops import (
    AgentHomeWorkspace,
    create_agent_home_file_tools,
    list_directory_tool,
    read_file_tool,
    search_file_tool,
    write_file_tool,
)
from agent.tools.builtin.terminal import AgentHomeCommandRunner, create_agent_home_terminal_tool, terminal_tool
from agent.tools.builtin.think import think_tool
from agent.tools.builtin.web import web_fetch_tool, web_search_tool
from agent.tools.registry import ToolRegistry

ALL_BUILTIN_TOOLS = [
    think_tool,
    read_file_tool,
    write_file_tool,
    list_directory_tool,
    search_file_tool,
    terminal_tool,
    web_search_tool,
    web_fetch_tool,
]

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
    registry = ToolRegistry()
    if home_client is None:
        tools = ALL_BUILTIN_TOOLS
    else:
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
