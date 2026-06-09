from pathlib import Path

import pytest

from agent.config import settings as settings_module
from agent.config.settings import AgentHomeSettings, load_settings, write_agent_home_credentials


def test_load_settings_requires_agent_id_when_no_config_exists(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_module, "DEFAULT_CONFIG_PATHS", [])

    with pytest.raises(RuntimeError, match="agent_home.agent_id is required"):
        load_settings(tmp_path / "missing.yaml")


def test_load_settings_requires_agent_id_when_config_omits_it(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  api_key: test-key\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="agent_home.agent_id is required"):
        load_settings(config_path)


def test_load_settings_uses_configured_agent_id(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "agent_home:\n  agent_id: l-agent:configured\n  token: tok\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.agent_home.agent_id == "l-agent:configured"
    assert settings.agent_home.token == "tok"


def test_load_settings_uses_agent_file_path(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "agent:\n"
        "  agent_file_path: /AGENT.md\n"
        "agent_home:\n"
        "  agent_id: l-agent:configured\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.agent.agent_file_path == "/AGENT.md"
    assert "guidance_file" not in settings.agent.__dataclass_fields__


def test_agent_home_settings_no_longer_has_enabled_flag():
    assert "enabled" not in AgentHomeSettings.__dataclass_fields__
    assert not hasattr(AgentHomeSettings(), "enabled")


def test_write_agent_home_credentials_preserves_existing_agent_id(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "agent_home:\n  agent_id: existing-agent\n  token: old-token\n",
        encoding="utf-8",
    )

    write_agent_home_credentials(config_path, "new-token")

    settings = load_settings(config_path)
    assert settings.agent_home.agent_id == "existing-agent"
    assert settings.agent_home.token == "new-token"
