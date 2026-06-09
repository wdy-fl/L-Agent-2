import asyncio
import importlib
from pathlib import Path

from rich.console import Console

from agent.cli.commands import CommandDispatcher
from agent.core.factory import build_runner
from agent.core.lifecycle import HookPhase


class FakeHome:
    def __init__(self):
        self.sessions = []
        self.created = False

    def create_session(self, session):
        session.active_branch_id = "b1"
        self.sessions.append(session)
        self.created = True

    def create_branch(self, branch):
        del branch
        return None

    def list_sessions(self):
        return self.sessions

    def get_messages_by_branch(self, branch_id):
        del branch_id
        return []

    def get_checkpoints_by_branch(self, branch_id):
        del branch_id
        return []


def test_new_command_uses_agent_home_store():
    home = FakeHome()
    dispatcher = CommandDispatcher(home, Console(record=True))

    asyncio.run(dispatcher.dispatch("/new"))

    assert home.created is True
    assert dispatcher.session_id
    assert dispatcher.branch_id == "b1"


def test_factory_registers_timeline_creation_before_finalize(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  api_key: test-key\nagent_home:\n  agent_id: l-agent:test\n", encoding="utf-8")

    runner = build_runner(config_path, home_client=FakeHome())
    names = [step.name for step in runner._registry.get_steps(HookPhase.before_agent)]

    assert "context.initialize" in names
    assert "run.create" in names
    assert "message.commit_user" in names
    assert "checkpoint.create_user_snapshot" in names
    assert names.index("context.initialize") < names.index("run.create")
    assert names.index("run.create") < names.index("message.commit_user")
    assert names.index("message.commit_user") < names.index("checkpoint.create_user_snapshot")


def test_main_uses_workspace_config_path_when_config_is_omitted(monkeypatch, tmp_path):
    cli_app = importlib.import_module("agent.cli.app")
    from agent.config.settings import Settings

    legacy_default_config = tmp_path / "home" / "config.yaml"
    legacy_default_config.parent.mkdir(parents=True)
    legacy_default_config.write_text("llm:\n  api_key: test-key\n", encoding="utf-8")
    calls = {}

    def fake_load_settings(config_path=None):
        del config_path
        return Settings(config_dir=Path("workspace"))

    def fake_initialize_agent_home(settings, config_path):
        del settings
        calls["config_path"] = config_path
        return FakeHome()

    def fake_build_runner(config_path, home_client=None):
        del config_path, home_client
        return object()

    monkeypatch.setattr(cli_app, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli_app, "initialize_agent_home", fake_initialize_agent_home)
    monkeypatch.setattr(cli_app, "build_runner", fake_build_runner)

    class FakeCLISession:
        def __init__(self, runner, store, config_path=None):
            del runner, store, config_path

        async def start(self, session_id=None):
            del session_id

    monkeypatch.setattr(cli_app, "CLISession", FakeCLISession)

    cli_app.main(session=None, config=None)

    assert calls["config_path"] == Path("workspace/config.yaml")


def test_cli_module_no_longer_imports_sqlite_timeline_store():
    import inspect

    cli_app = importlib.import_module("agent.cli.app")
    source = inspect.getsource(cli_app)

    assert "SQLiteTimelineStore" not in source
    assert "workspace/timeline.db" not in source
