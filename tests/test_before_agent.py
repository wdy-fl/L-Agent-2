import pytest

from agent.core.context import RunContext
from agent.llm.types import ModelConfig
from agent.storage.sqlite import SQLiteTimelineStore
from agent.steps.before_agent import ContextInitialize, MemoryPrefetch, MessageCommitUser
from agent.timeline.session_factory import create_session_with_default_branch


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


def test_context_initialize_creates_persisted_system_message_for_new_session():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    step = ContextInitialize(guidance="Use Agent Home.", model_config=ModelConfig(model="test-model"))

    step.run(ctx)

    assert ctx.model_config.model == "test-model"
    assert ctx.messages == [{"role": "system", "content": "Use Agent Home."}]
    persisted = store.get_messages_by_branch(session.active_branch_id)
    assert len(persisted) == 1
    assert persisted[0].role == "system"
    assert persisted[0].content == "Use Agent Home."
    assert persisted[0].run_id == ctx.run_id


def test_context_initialize_loads_history_without_loading_guidance():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    first_ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    ContextInitialize(guidance="First guidance").run(first_ctx)

    second_ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
        home_client=FakeHomeClient({}),
    )
    step = ContextInitialize(agent_file_path="/AGENT.md")

    step.run(second_ctx)

    assert second_ctx.messages == [{"role": "system", "content": "First guidance"}]
    assert second_ctx.home_client.read_paths == []


def test_message_commit_user_appends_enhanced_input_after_context_initialize_history():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    first_ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    ContextInitialize(guidance="First guidance").run(first_ctx)

    ctx = RunContext(
        input="hello",
        enhanced_input="hello\n\nMemory:\n- [fact] remembered",
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )

    ContextInitialize(guidance="Ignored guidance").run(ctx)
    MessageCommitUser().run(ctx)

    assert ctx.messages == [
        {"role": "system", "content": "First guidance"},
        {"role": "user", "content": "hello\n\nMemory:\n- [fact] remembered"},
    ]
    persisted = store.get_messages_by_branch(session.active_branch_id)
    assert len(persisted) == 2
    assert persisted[1].role == "user"
    assert persisted[1].content == "hello\n\nMemory:\n- [fact] remembered"


def test_context_initialize_loads_agent_file_from_agent_home():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
        home_client=FakeHomeClient({"/AGENT.md": "  Use Agent Home.\n"}),
    )
    step = ContextInitialize(
        agent_file_path="/AGENT.md",
        model_config=ModelConfig(model="test-model"),
    )

    step.run(ctx)

    assert not hasattr(ctx, "base_model_context")
    assert ctx.model_config.model == "test-model"
    assert ctx.messages == [{"role": "system", "content": "Use Agent Home."}]
    assert ctx.home_client.read_paths == ["/AGENT.md"]


def test_context_initialize_keeps_inline_guidance_when_agent_file_path_empty():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    step = ContextInitialize(guidance="Inline guidance")

    step.run(ctx)

    assert not hasattr(ctx, "base_model_context")
    assert ctx.messages == [{"role": "system", "content": "Inline guidance"}]


def test_context_initialize_requires_timeline_store():
    ctx = RunContext(session_id="s", branch_id="b")
    step = ContextInitialize(guidance="Use Agent Home.")

    with pytest.raises(RuntimeError, match="timeline_store is required"):
        step.run(ctx)


def test_context_initialize_requires_session_id():
    store = SQLiteTimelineStore(":memory:")
    ctx = RunContext(branch_id="b", timeline_store=store)
    step = ContextInitialize(guidance="Use Agent Home.")

    with pytest.raises(RuntimeError, match="session_id is required"):
        step.run(ctx)


def test_context_initialize_requires_branch_id():
    store = SQLiteTimelineStore(":memory:")
    ctx = RunContext(session_id="s", timeline_store=store)
    step = ContextInitialize(guidance="Use Agent Home.")

    with pytest.raises(RuntimeError, match="branch_id is required"):
        step.run(ctx)


def test_context_initialize_requires_home_client_for_agent_file_path():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    step = ContextInitialize(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)


def test_context_initialize_wraps_agent_home_read_errors():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
        home_client=FakeHomeClient({}),
    )
    step = ContextInitialize(agent_file_path="/AGENT.md")

    with pytest.raises(RuntimeError, match="Failed to load agent file from Agent Home workspace: /AGENT.md"):
        step.run(ctx)
