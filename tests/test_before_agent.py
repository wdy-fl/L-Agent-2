import pytest

from agent.core.context import RunContext
from agent.llm.types import ModelConfig
from agent.steps.before_agent import ContextInitialize, MemoryPrefetch, MessageCommitUser


class FakeHomeClient:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.read_paths: list[str] = []

    def workspace_get_text(self, path: str) -> str:
        self.read_paths.append(path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class FakeMemoryClient:
    def search_memory(self, query: str) -> list[dict[str, str]]:
        return [{"type": "fact", "content": f"remembered for {query}"}]


def test_message_commit_user_initializes_visible_messages_without_timeline_store():
    ctx = RunContext(input="hello")
    step = MessageCommitUser()

    step.run(ctx)

    assert ctx.messages == [{"role": "user", "content": "hello"}]


def test_memory_prefetch_before_message_commit_user_commits_enhanced_input():
    ctx = RunContext(input="hello", home_client=FakeMemoryClient())

    MemoryPrefetch().run(ctx)
    MessageCommitUser().run(ctx)

    assert ctx.messages == [
        {"role": "user", "content": "hello\n\nMemory:\n- [fact] remembered for hello"}
    ]


def test_run_context_exposes_direct_model_request_fields():
    ctx = RunContext()

    assert hasattr(ctx, "model_config")
    assert hasattr(ctx, "available_tools")
    assert hasattr(ctx, "enhanced_input")
    assert not hasattr(ctx, "base_model_context")


def test_context_initialize_loads_agent_file_from_agent_home():
    ctx = RunContext(home_client=FakeHomeClient({"/AGENT.md": "  Use Agent Home.\n"}))
    step = ContextInitialize(
        agent_file_path="/AGENT.md",
        model_config=ModelConfig(model="test-model"),
    )

    step.run(ctx)

    assert not hasattr(ctx, "base_model_context")
    assert ctx.model_config.model == "test-model"
    assert ctx.home_client.read_paths == ["/AGENT.md"]


def test_context_initialize_keeps_inline_guidance_when_agent_file_path_empty():
    ctx = RunContext()
    step = ContextInitialize(guidance="Inline guidance")

    step.run(ctx)

    assert not hasattr(ctx, "base_model_context")


def test_context_initialize_requires_home_client_for_agent_file_path():
    ctx = RunContext()
    step = ContextInitialize(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)


def test_context_initialize_wraps_agent_home_read_errors():
    ctx = RunContext(home_client=FakeHomeClient({}))
    step = ContextInitialize(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)
