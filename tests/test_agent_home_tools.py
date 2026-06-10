import pytest

from agent.tools.base import ToolCall, ToolPlan, ToolResultStatus
from agent.tools.builtin import create_builtin_registry
from agent.tools.builtin.file_ops import create_agent_home_file_tools
from agent.tools.builtin.terminal import create_agent_home_terminal_tool
from agent.tools.dispatcher import ToolDispatcher


class FakeHome:
    def __init__(self):
        self.files = {}
        self.commands = []
        self.reads = []
        self.writes = []
        self.lists = []

    def workspace_put(self, path, content):
        self.writes.append((path, content))
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        return {"path": path, "size": len(self.files[path])}

    def workspace_get_text(self, path):
        self.reads.append(path)
        return self.files[path].decode("utf-8")

    def workspace_list(self, prefix):
        self.lists.append(prefix)
        return [
            {"name": path.split("/")[-1], "type": "file", "size": len(body)}
            for path, body in sorted(self.files.items())
            if path.startswith(prefix)
        ]

    def workspace_run_command(self, command, timeout_seconds=120, env=None):
        self.commands.append((command, timeout_seconds, env or {}))
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "changed_paths": ["/notes/todo.md"]}


def test_agent_home_file_tools_read_write_list_search():
    home = FakeHome()
    tools = {tool.name: tool for tool in create_agent_home_file_tools(home)}

    assert "Written 5 bytes to /notes/todo.md" == tools["write_file"].handler("/notes/todo.md", "hello")
    assert "1\thello" == tools["read_file"].handler("/notes/todo.md")
    assert "/notes/todo.md" in tools["list_directory"].handler("/notes")
    assert "/notes/todo.md:1: hello" in tools["search_file"].handler("hello", "/notes")


def test_agent_home_file_tool_metadata_uses_logical_workspace_paths():
    home = FakeHome()
    tools = {tool.name: tool for tool in create_agent_home_file_tools(home)}

    assert "/notes/todo.md" in tools["read_file"].parameters_schema["properties"]["file_path"]["description"]
    assert "Absolute path" not in tools["read_file"].parameters_schema["properties"]["file_path"]["description"]


def test_agent_home_list_directory_schema_does_not_advertise_recursive():
    home = FakeHome()
    tools = {tool.name: tool for tool in create_agent_home_file_tools(home)}

    assert "recursive" not in tools["list_directory"].parameters_schema["properties"]


def test_agent_home_terminal_tool_uses_workspace_command_api():
    home = FakeHome()
    tool = create_agent_home_terminal_tool(home)

    result = tool.handler("printf ok", timeout=10)

    assert "cwd" not in tool.parameters_schema["properties"]
    assert "Agent-Home workspace sandbox" in tool.description
    assert home.commands == [("printf ok", 10, {})]
    assert "ok" in result
    assert "[exit_code: 0]" in result
    assert "[changed_paths] /notes/todo.md" in result


def test_builtin_registry_with_home_does_not_register_local_tool_instances():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)

    assert registry.get("read_file") is not None
    assert registry.get("terminal") is not None


def test_builtin_registry_requires_home_client():
    with pytest.raises(RuntimeError, match="Agent Home client is required"):
        create_builtin_registry(home_client=None)


def test_builtin_registry_with_home_exposes_expected_tools_and_schemas():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)

    expected_tool_names = {
        "think",
        "read_file",
        "write_file",
        "list_directory",
        "search_file",
        "terminal",
        "web_search",
        "web_fetch",
    }

    assert {schema["function"]["name"] for schema in registry.list_schemas()} == expected_tool_names
    for tool_name in expected_tool_names:
        assert registry.get(tool_name) is not None

    for schema in registry.list_schemas():
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert "required" in func["parameters"]


def test_dispatcher_read_file_uses_agent_home_workspace_client():
    home = FakeHome()
    home.workspace_put("/notes/test.txt", "content here\n")
    registry = create_builtin_registry(home_client=home)
    dispatcher = ToolDispatcher(registry)
    plan = ToolPlan(calls=[
        ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": "/notes/test.txt"}),
    ])

    results = dispatcher.dispatch(plan)

    assert results[0].status == ToolResultStatus.success
    assert "content here" in results[0].content
    assert home.reads == ["/notes/test.txt"]


def test_dispatcher_agent_home_errors_stay_internal():
    home = FakeHome()
    registry = create_builtin_registry(home_client=home)
    dispatcher = ToolDispatcher(registry)
    plan = ToolPlan(calls=[
        ToolCall(call_id="tc1", tool_name="read_file", arguments={"file_path": "/no/such/file"}),
    ])

    results = dispatcher.dispatch(plan)

    assert results[0].status == ToolResultStatus.error
    assert "Tool execution error" in results[0].content
    assert "KeyError" in results[0].content
