from agent.cli.config import load_approval_config


def test_load_approval_config_uses_defaults_when_approval_section_missing(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  api_key: dummy\n", encoding="utf-8")

    config = load_approval_config(config_path)

    assert config.auto_approve == ["think", "read_file", "list_directory"]
    assert config.always_confirm == ["terminal", "write_file"]
