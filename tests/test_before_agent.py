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


class FakeMemoryStore(SQLiteTimelineStore):
    def __init__(self, memories: list[dict[str, str]] | None = None) -> None:
        super().__init__(":memory:")
        self.memories = memories or []
        self.queries: list[str] = []

    def search_memory(self, query: str) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.memories


class FakeMemoryClient:
    def __init__(self, memories: list[dict[str, str]] | None = None) -> None:
        self.memories = memories or []
        self.queries: list[str] = []

    def search_memory(self, query: str) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.memories


def test_memory_prefetch_sets_enhanced_input_to_raw_input_when_no_memory():
    memory = FakeMemoryClient()
    ctx = RunContext(input="hello", home_client=memory)

    MemoryPrefetch(limit=5).run(ctx)

    assert memory.queries == ["hello"]
    assert ctx.enhanced_input == "hello"


def test_memory_prefetch_adds_memory_block_to_enhanced_input():
    memory = FakeMemoryClient(
        [
            {"type": "user", "content": "Prefers concise answers."},
            {"type": "project", "content": "Uses python3."},
        ]
    )
    ctx = RunContext(input="hello", home_client=memory)

    MemoryPrefetch(limit=5).run(ctx)

    assert memory.queries == ["hello"]
    assert ctx.enhanced_input == (
        "<memory>\n"
        "- [user] Prefers concise answers.\n"
        "- [project] Uses python3.\n"
        "</memory>\n\n"
        "<user>\n"
        "hello\n"
        "</user>"
    )


def test_memory_prefetch_missing_search_memory_raises():
    ctx = RunContext(input="hello")

    with pytest.raises(RuntimeError, match="search_memory is required"):
        MemoryPrefetch().run(ctx)


def test_message_commit_user_appends_and_persists_enhanced_input_to_existing_messages():
    store = FakeMemoryStore()
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        input="hello",
        enhanced_input="<user>\nhello\n</user>",
        messages=[{"role": "system", "content": "Use Agent Home."}],
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )

    MessageCommitUser().run(ctx)

    assert ctx.messages == [
        {"role": "system", "content": "Use Agent Home."},
        {"role": "user", "content": "<user>\nhello\n</user>"},
    ]
    persisted = store.get_messages_by_branch(session.active_branch_id)
    assert len(persisted) == 1
    assert persisted[0].role == "user"
    assert persisted[0].content == "<user>\nhello\n</user>"


def test_message_commit_user_missing_requirements_raise():
    store = FakeMemoryStore()
    session = create_session_with_default_branch(store)

    missing_store = RunContext(
        enhanced_input="enhanced",
        messages=[{"role": "system", "content": "Use Agent Home."}],
        session_id=session.session_id,
        branch_id=session.active_branch_id,
    )
    with pytest.raises(RuntimeError, match="timeline_store is required"):
        MessageCommitUser().run(missing_store)

    missing_session = RunContext(
        enhanced_input="enhanced",
        messages=[{"role": "system", "content": "Use Agent Home."}],
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    with pytest.raises(RuntimeError, match="session_id is required"):
        MessageCommitUser().run(missing_session)

    missing_branch = RunContext(
        enhanced_input="enhanced",
        messages=[{"role": "system", "content": "Use Agent Home."}],
        session_id=session.session_id,
        timeline_store=store,
    )
    with pytest.raises(RuntimeError, match="branch_id is required"):
        MessageCommitUser().run(missing_branch)

    missing_enhanced_input = RunContext(
        input="hello",
        messages=[{"role": "system", "content": "Use Agent Home."}],
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    with pytest.raises(RuntimeError, match="enhanced_input is required"):
        MessageCommitUser().run(missing_enhanced_input)


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
        enhanced_input="<memory>\n- [fact] remembered\n</memory>\n\n<user>\nhello\n</user>",
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )

    ContextInitialize(guidance="Ignored guidance").run(ctx)
    MessageCommitUser().run(ctx)

    assert ctx.messages == [
        {"role": "system", "content": "First guidance"},
        {"role": "user", "content": "<memory>\n- [fact] remembered\n</memory>\n\n<user>\nhello\n</user>"},
    ]
    persisted = store.get_messages_by_branch(session.active_branch_id)
    assert len(persisted) == 2
    assert persisted[1].role == "user"
    assert persisted[1].content == "<memory>\n- [fact] remembered\n</memory>\n\n<user>\nhello\n</user>"


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
