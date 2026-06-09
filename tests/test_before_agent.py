import pytest

from agent.core.context import RunContext
from agent.llm.types import ModelConfig
from agent.steps.before_agent import BaseContextLoadStaticParts


class FakeHomeClient:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.read_paths: list[str] = []

    def workspace_get_text(self, path: str) -> str:
        self.read_paths.append(path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


def test_load_static_parts_loads_agent_file_from_agent_home():
    ctx = RunContext(home_client=FakeHomeClient({"/AGENT.md": "  Use Agent Home.\n"}))
    step = BaseContextLoadStaticParts(
        agent_file_path="/AGENT.md",
        model_config=ModelConfig(model="test-model"),
    )

    step.run(ctx)

    assert ctx.base_model_context is not None
    assert ctx.base_model_context.guidance == "Use Agent Home."
    assert ctx.base_model_context.model_config.model == "test-model"
    assert ctx.home_client.read_paths == ["/AGENT.md"]


def test_load_static_parts_keeps_inline_guidance_when_agent_file_path_empty():
    ctx = RunContext()
    step = BaseContextLoadStaticParts(guidance="Inline guidance")

    step.run(ctx)

    assert ctx.base_model_context is not None
    assert ctx.base_model_context.guidance == "Inline guidance"


def test_load_static_parts_requires_home_client_for_agent_file_path():
    ctx = RunContext()
    step = BaseContextLoadStaticParts(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)


def test_load_static_parts_wraps_agent_home_read_errors():
    ctx = RunContext(home_client=FakeHomeClient({}))
    step = BaseContextLoadStaticParts(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)
