# Session Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ctx.messages` the single source of truth for session conversation context, with a persisted first system message and fail-fast timeline-backed message lifecycle.

**Architecture:** Remove `BaseModelContext` and move system/history initialization into `ContextInitialize`. Store model configuration, available tools, and memory-enhanced input directly on `RunContext`; compose model requests directly from those fields.

**Tech Stack:** Python 3, dataclasses, pytest, existing `AgentRunner` lifecycle steps, `SQLiteTimelineStore`.

---

## File Structure

- Modify `agent/llm/types.py`: remove `BaseModelContext`; keep `ModelConfig`, `ModelRequest`, `ModelResponse`, and tool/usage types.
- Modify `agent/core/context.py`: replace `base_model_context` with `model_config`, `available_tools`, and `enhanced_input` fields.
- Modify `agent/steps/before_agent.py`: update `ContextInitialize`, `MemoryPrefetch`, `ToolsSnapshotAvailableTools`, and `MessageCommitUser` for timeline-backed messages.
- Modify `agent/steps/before_model.py`: simplify `ModelRequestCompose` to use `ctx.messages` directly.
- Modify `agent/core/factory.py`: preserve production step order and pass model config/tool registry to updated steps.
- Modify `tests/test_before_agent.py`: replace no-store tests with store-backed initialization, memory, and user commit tests.
- Modify `tests/test_timeline_resume.py`: update helper registry and add second-turn model-request coverage.
- Modify other tests only if imports or no-store assumptions break.

---

### Task 1: Update RunContext And Model Types

**Files:**
- Modify: `agent/llm/types.py`
- Modify: `agent/core/context.py`
- Test: `tests/test_before_agent.py`

- [ ] **Step 1: Write failing context shape test**

Add this test to `tests/test_before_agent.py` near the existing context initialization tests:

```python
def test_run_context_exposes_direct_model_request_fields():
    ctx = RunContext()

    assert hasattr(ctx, "model_config")
    assert hasattr(ctx, "available_tools")
    assert hasattr(ctx, "enhanced_input")
    assert not hasattr(ctx, "base_model_context")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_before_agent.py::test_run_context_exposes_direct_model_request_fields -v`

Expected: FAIL because `RunContext` still has `base_model_context` and does not yet expose all direct fields.

- [ ] **Step 3: Remove BaseModelContext and add direct fields**

In `agent/llm/types.py`, delete the entire `BaseModelContext` dataclass. Keep `ModelConfig` as the first dataclass in the file.

In `agent/core/context.py`, update imports:

```python
from agent.llm.types import ModelConfig, ModelRequest, ModelResponse
```

Replace the model context section with:

```python
    # --- model request state ---
    model_config: ModelConfig = field(default_factory=ModelConfig)
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    current_model_request: ModelRequest | None = None
    current_model_response: ModelResponse | None = None
```

Add this field under the basic input fields:

```python
    enhanced_input: str = ""
```

Remove the `base_model_context` field entirely.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_before_agent.py::test_run_context_exposes_direct_model_request_fields -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/llm/types.py agent/core/context.py tests/test_before_agent.py
git commit -m "refactor: expose model request fields on run context"
```

---

### Task 2: Make ContextInitialize Load History Or Persist System

**Files:**
- Modify: `agent/steps/before_agent.py`
- Modify: `tests/test_before_agent.py`

- [ ] **Step 1: Replace no-store initialization tests with store-backed tests**

In `tests/test_before_agent.py`, add imports:

```python
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.session_factory import create_session_with_default_branch
```

Replace the old context initialization tests with these tests:

```python
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
```

Keep the existing `FakeHomeClient` class for agent file tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_before_agent.py -v`

Expected: FAIL because `ContextInitialize` still writes `base_model_context`, does not load history, does not persist system messages, and no-store behavior has not changed.

- [ ] **Step 3: Implement timeline-backed ContextInitialize**

In `agent/steps/before_agent.py`, update imports:

```python
from agent.timeline.resume import resume
```

Remove `BaseModelContext` from imports.

Update `ContextInitialize.run()` to:

```python
    def run(self, ctx: RunContext) -> None:
        if not ctx.run_id:
            ctx.run_id = str(uuid.uuid4())
        ctx.iterations = []
        ctx.iteration_index = 0
        ctx.status = "running"
        ctx.model_config = self._model_config

        if ctx.messages:
            return

        if ctx.timeline_store is None:
            raise RuntimeError("timeline_store is required")
        if not ctx.session_id:
            raise RuntimeError("session_id is required")
        if not ctx.branch_id:
            raise RuntimeError("branch_id is required")

        result = resume(ctx.timeline_store, ctx.session_id)
        ctx.messages = [_message_to_dict(message) for message in result.messages]
        if ctx.messages:
            return

        guidance = self._guidance
        if self._agent_file_path:
            guidance = self._load_agent_file(ctx)

        system_message = {"role": "system", "content": guidance}
        ctx.messages.append(system_message)

        seq = ctx.timeline_store.get_latest_sequence(ctx.branch_id) + 1
        ctx.timeline_store.append_message(Message(
            message_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            sequence=seq,
            role="system",
            content=guidance,
        ))
```

Add this helper in `agent/steps/before_agent.py` above `ContextInitialize`:

```python
def _message_to_dict(message: Message) -> dict[str, Any]:
    data: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        data["tool_calls"] = message.tool_calls
    if message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_before_agent.py -v`

Expected: PASS for context initialization tests; memory and user commit tests may still fail if they still assert old behavior.

- [ ] **Step 5: Commit**

```bash
git add agent/steps/before_agent.py tests/test_before_agent.py
git commit -m "feat: initialize session messages from timeline"
```

---

### Task 3: Refactor MemoryPrefetch And User Message Commit

**Files:**
- Modify: `agent/steps/before_agent.py`
- Modify: `tests/test_before_agent.py`

- [ ] **Step 1: Add memory and enhanced user message tests**

Add these tests to `tests/test_before_agent.py`:

```python
class FakeMemoryStore(SQLiteTimelineStore):
    def __init__(self, memories: list[dict[str, str]]) -> None:
        super().__init__(":memory:")
        self.memories = memories
        self.queries: list[str] = []

    def search_memory(self, query: str) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.memories


def test_memory_prefetch_sets_enhanced_input_to_raw_input_when_no_memory():
    store = FakeMemoryStore([])
    ctx = RunContext(input="hello", timeline_store=store)
    step = MemoryPrefetch(limit=5)

    step.run(ctx)

    assert store.queries == ["hello"]
    assert ctx.enhanced_input == "hello"


def test_memory_prefetch_adds_memory_block_to_enhanced_input():
    store = FakeMemoryStore([{"type": "user", "content": "Prefers concise answers."}])
    ctx = RunContext(input="hello", timeline_store=store)
    step = MemoryPrefetch(limit=5)

    step.run(ctx)

    assert ctx.enhanced_input == "<memory>\n- [user] Prefers concise answers.\n</memory>\n\n<user>\nhello\n</user>"


def test_message_commit_user_appends_and_persists_enhanced_input():
    store = SQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    ctx = RunContext(
        input="raw hello",
        enhanced_input="enhanced hello",
        session_id=session.session_id,
        branch_id=session.active_branch_id,
        timeline_store=store,
    )
    ContextInitialize(guidance="System").run(ctx)
    RunCreate().run(ctx)
    step = MessageCommitUser()

    step.run(ctx)

    assert ctx.messages[-1] == {"role": "user", "content": "enhanced hello"}
    persisted = store.get_messages_by_branch(session.active_branch_id)
    assert persisted[-1].role == "user"
    assert persisted[-1].content == "enhanced hello"
    assert persisted[-1].run_id == ctx.run_id
```

Update imports in `tests/test_before_agent.py` to include `MemoryPrefetch` and `RunCreate`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_before_agent.py -v`

Expected: FAIL because `MemoryPrefetch` still writes `memory_context`, and `MessageCommitUser` does not use `enhanced_input` correctly.

- [ ] **Step 3: Implement MemoryPrefetch enhanced input**

Replace `MemoryPrefetch.run()` in `agent/steps/before_agent.py` with:

```python
    def run(self, ctx: RunContext) -> None:
        search_memory = None
        for store in (ctx.home_client, ctx.timeline_store):
            candidate = getattr(store, "search_memory", None)
            if callable(candidate):
                search_memory = candidate
                break
        if search_memory is None:
            raise RuntimeError("search_memory is required")

        search = cast(Callable[[str], list[dict[str, Any]]], search_memory)
        memories = search(ctx.input)[: self._limit]
        if not memories:
            ctx.enhanced_input = ctx.input
            return

        memory_lines = [
            f"- [{memory.get('type', '')}] {memory.get('content', '')}"
            for memory in memories
        ]
        ctx.enhanced_input = "<memory>\n" + "\n".join(memory_lines) + "\n</memory>\n\n<user>\n" + ctx.input + "\n</user>"
```

- [ ] **Step 4: Implement MessageCommitUser enhanced input persistence**

Replace `MessageCommitUser.run()` with:

```python
    def run(self, ctx: RunContext) -> None:
        if ctx.timeline_store is None:
            raise RuntimeError("timeline_store is required")
        if not ctx.session_id:
            raise RuntimeError("session_id is required")
        if not ctx.branch_id:
            raise RuntimeError("branch_id is required")
        if not ctx.enhanced_input:
            raise RuntimeError("enhanced_input is required")

        ctx.messages.append({"role": "user", "content": ctx.enhanced_input})

        seq = ctx.timeline_store.get_latest_sequence(ctx.branch_id) + 1
        msg = Message(
            message_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            sequence=seq,
            role="user",
            content=ctx.enhanced_input,
        )
        ctx.timeline_store.append_message(msg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_before_agent.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/steps/before_agent.py tests/test_before_agent.py
git commit -m "feat: persist memory-enhanced user messages"
```

---

### Task 4: Simplify Tool Snapshot And Model Request Compose

**Files:**
- Modify: `agent/steps/before_agent.py`
- Modify: `agent/steps/before_model.py`
- Modify: `tests/test_before_agent.py`
- Modify: `tests/test_model_call_pipeline.py`

- [ ] **Step 1: Add direct model request compose test**

In `tests/test_before_agent.py`, import `ModelRequestCompose` and add:

```python
def test_model_request_compose_uses_messages_tools_and_model_config_directly():
    ctx = RunContext(messages=[{"role": "system", "content": "System"}])
    ctx.available_tools = [{"type": "function", "function": {"name": "think", "parameters": {"type": "object"}}}]
    ctx.model_config = ModelConfig(model="test-model", temperature=0.2, max_tokens=123)

    ModelRequestCompose().run(ctx)

    assert ctx.current_model_request is not None
    assert ctx.current_model_request.messages == [{"role": "system", "content": "System"}]
    assert ctx.current_model_request.tools == ctx.available_tools
    assert ctx.current_model_request.model == "test-model"
    assert ctx.current_model_request.temperature == 0.2
    assert ctx.current_model_request.max_tokens == 123
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_before_agent.py::test_model_request_compose_uses_messages_tools_and_model_config_directly -v`

Expected: FAIL because `ModelRequestCompose` still reads `base_model_context`.

- [ ] **Step 3: Update ToolsSnapshotAvailableTools**

In `agent/steps/before_agent.py`, replace `ToolsSnapshotAvailableTools.run()` with:

```python
    def run(self, ctx: RunContext) -> None:
        if self._registry is None:
            ctx.available_tools = []
        else:
            ctx.available_tools = self._registry.list_schemas()
```

- [ ] **Step 4: Update ModelRequestCompose**

In `agent/steps/before_model.py`, replace `ModelRequestCompose.run()` with:

```python
    def run(self, ctx: RunContext) -> None:
        ctx.current_model_request = ModelRequest(
            messages=ctx.messages,
            tools=ctx.available_tools,
            model=ctx.model_config.model,
            temperature=ctx.model_config.temperature,
            max_tokens=ctx.model_config.max_tokens,
        )
```

- [ ] **Step 5: Run targeted tests**

Run: `pytest tests/test_before_agent.py::test_model_request_compose_uses_messages_tools_and_model_config_directly -v`

Expected: PASS.

Run: `pytest tests/test_model_call_pipeline.py -v`

Expected: PASS, or FAIL only where tests still construct `base_model_context`; update those tests to set `ctx.model_config`, `ctx.available_tools`, and `ctx.messages` directly.

- [ ] **Step 6: Commit**

```bash
git add agent/steps/before_agent.py agent/steps/before_model.py tests/test_before_agent.py tests/test_model_call_pipeline.py
git commit -m "refactor: compose model requests from session messages"
```

---

### Task 5: Update Factory And Lifecycle Tests

**Files:**
- Modify: `agent/core/factory.py`
- Modify: `tests/test_timeline_resume.py`
- Modify: `tests/test_cli_events.py`
- Modify: affected tests from full test run

- [ ] **Step 1: Update factory imports and registration**

In `agent/core/factory.py`, ensure `ContextInitialize` is registered with `agent_file_path` and `model_config`, and step order is:

```python
    reg.register(ContextInitialize(
        agent_file_path=settings.agent.agent_file_path,
        model_config=model_config,
    ))
    reg.register(RunCreate())
    reg.register(MemoryPrefetch(limit=settings.agent_home.memory_prefetch_limit))
    reg.register(MessageCommitUser())
    reg.register(CheckpointCreateUserSnapshot())
    reg.register(ToolsSnapshotAvailableTools(registry=tool_registry))
    reg.register(BudgetInitialize(
        max_iterations=settings.budget.max_iterations,
        max_tokens=settings.budget.max_tokens,
    ))
```

- [ ] **Step 2: Update helper registries in tests**

In `tests/test_timeline_resume.py` and `tests/test_cli_events.py`, update helper registries so `MemoryPrefetch` appears before `MessageCommitUser` when those tests exercise normal message flow.

For tests that do not need memory, use a store with `search_memory()` support. Add this helper in each test file if needed:

```python
class MemorySQLiteTimelineStore(SQLiteTimelineStore):
    def search_memory(self, query: str) -> list[dict[str, str]]:
        return []
```

Replace `SQLiteTimelineStore(":memory:")` with `MemorySQLiteTimelineStore(":memory:")` for normal lifecycle tests that include `MemoryPrefetch`.

- [ ] **Step 3: Add multi-turn request coverage**

Add this test to `tests/test_timeline_resume.py`:

```python
async def test_second_turn_model_request_contains_loaded_history_and_current_user():
    store = MemorySQLiteTimelineStore(":memory:")
    session = create_session_with_default_branch(store)
    branch_id = session.active_branch_id
    seen_requests: list[list[dict]] = []

    reg = _build_full_registry()
    reg.register(ModelRequestCompose())

    def model_fn(c: RunContext):
        assert c.current_model_request is not None
        seen_requests.append(c.current_model_request.messages.copy())
        return ModelResponse(content=f"reply to: {c.input}", usage=Usage(input_tokens=5, output_tokens=3))

    runner = AgentRunner(registry=reg, middleware_chain=MiddlewareChain(), model_call=model_fn)

    await runner.run_to_completion(RunContext(
        input="first",
        session_id=session.session_id,
        branch_id=branch_id,
        timeline_store=store,
    ))
    await runner.run_to_completion(RunContext(
        input="second",
        session_id=session.session_id,
        branch_id=branch_id,
        timeline_store=store,
    ))

    second_messages = seen_requests[1]
    assert [message["role"] for message in second_messages] == ["system", "user", "assistant", "user"]
    assert second_messages[1]["content"] == "first"
    assert second_messages[2]["content"] == "reply to: first"
    assert second_messages[3]["content"] == "second"
```

Add imports for `ModelRequestCompose` if missing.

- [ ] **Step 4: Run targeted lifecycle tests**

Run: `pytest tests/test_timeline_resume.py tests/test_cli_events.py -v`

Expected: PASS after updating store helpers and registries.

- [ ] **Step 5: Commit**

```bash
git add agent/core/factory.py tests/test_timeline_resume.py tests/test_cli_events.py
git commit -m "test: cover timeline-backed multi-turn context"
```

---

### Task 6: Remove Remaining BaseModelContext References And Run Full Tests

**Files:**
- Modify: any files returned by search
- Test: full test suite

- [ ] **Step 1: Search for removed type references**

Run: `rg "BaseModelContext|base_model_context|memory_context|workspace_context" agent tests`

Expected: no matches after cleanup, except references in old docs if intentionally retained. For source and test files, there must be no matches.

- [ ] **Step 2: Remove or rewrite any remaining source/test references**

For any source/test match, update it to direct `RunContext` fields:

```python
ctx.model_config = ModelConfig(model="test-model")
ctx.available_tools = []
ctx.messages = [{"role": "system", "content": "System"}]
```

- [ ] **Step 3: Run full tests**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 4: If tests fail, fix only failures caused by this refactor**

For failures about missing `search_memory`, provide the memory-capable store helper in that test file.

For failures about no `timeline_store`, update the test to create a store and session:

```python
store = SQLiteTimelineStore(":memory:")
session = create_session_with_default_branch(store)
ctx = RunContext(
    input="hello",
    session_id=session.session_id,
    branch_id=session.active_branch_id,
    timeline_store=store,
)
```

For failures about `base_model_context`, replace with `ctx.model_config`, `ctx.available_tools`, and `ctx.messages`.

- [ ] **Step 5: Run full tests again**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent tests
git commit -m "refactor: remove base model context lifecycle"
```

---

## Self-Review

- Spec coverage: covered removal of `BaseModelContext`, persisted system message, timeline history loading, memory-enhanced user messages, direct model request composition, assistant/tool double-write behavior, fail-fast missing dependency behavior, and store-backed tests.
- Placeholder scan: no `TBD`, `TODO`, or unspecified edge-case steps remain.
- Type consistency: plan uses `ctx.model_config`, `ctx.available_tools`, `ctx.enhanced_input`, `ctx.messages`, and existing `ModelConfig` consistently across tasks.
