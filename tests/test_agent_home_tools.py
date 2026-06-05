from agent.tools.builtin import create_builtin_registry
from agent.tools.builtin.file_ops import create_agent_home_file_tools
from agent.tools.builtin.terminal import create_agent_home_terminal_tool


class FakeHome:
    def __init__(self):
        self.files = {}
        self.commands = []

    def workspace_put(self, path, content):
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        return {"path": path, "size": len(self.files[path])}

    def workspace_get_text(self, path):
        return self.files[path].decode("utf-8")

    def workspace_list(self, prefix):
        return [{"path": path, "kind": "file", "size": len(body)} for path, body in sorted(self.files.items()) if path.startswith(prefix)]

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
