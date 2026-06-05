from __future__ import annotations

import uuid
from typing import Any, Callable, cast

from agent.core.context import BudgetState, RunContext
from agent.core.lifecycle import HookPhase
from agent.llm.types import BaseModelContext, ModelConfig
from agent.steps.base import Step
from agent.timeline.models import AgentRun, Checkpoint, CheckpointKind, Message
from agent.tools.registry import ToolRegistry


class ContextInitialize(Step):
    """Create RunContext basic fields, initialize empty iterations list."""

    def __init__(self) -> None:
        super().__init__("context.initialize", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        if not ctx.run_id:
            ctx.run_id = str(uuid.uuid4())
        ctx.iterations = []
        ctx.iteration_index = 0
        ctx.status = "running"


class InputNormalize(Step):
    """Normalize user input: strip whitespace, record raw input."""

    def __init__(self) -> None:
        super().__init__("input.normalize", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        ctx.raw_input = ctx.input
        ctx.input = ctx.input.strip()


class BaseContextLoadStaticParts(Step):
    """Load guidance / workspace into ctx.base_model_context."""

    def __init__(
        self,
        guidance: str = "",
        workspace_context: str = "",
        model_config: ModelConfig | None = None,
    ) -> None:
        super().__init__("base_context.load_static_parts", HookPhase.before_agent)
        self._guidance = guidance
        self._workspace_context = workspace_context
        self._model_config = model_config or ModelConfig()

    def run(self, ctx: RunContext) -> None:
        ctx.base_model_context = BaseModelContext(
            guidance=self._guidance,
            workspace_context=self._workspace_context,
            model_config=self._model_config,
        )


class MemoryPrefetch(Step):
    """Prefetch matching memories into base model context."""

    def __init__(self, limit: int = 5) -> None:
        super().__init__("memory.prefetch", HookPhase.before_agent)
        self._limit = limit

    def run(self, ctx: RunContext) -> None:
        if ctx.base_model_context is None:
            return
        search_memory = None
        for store in (ctx.home_client, ctx.timeline_store):
            candidate = getattr(store, "search_memory", None)
            if callable(candidate):
                search_memory = candidate
                break
        if search_memory is None:
            ctx.base_model_context.memory_context = None
            return
        search = cast(Callable[[str], list[dict[str, Any]]], search_memory)
        memories = search(ctx.input)[: self._limit]
        if not memories:
            ctx.base_model_context.memory_context = None
            return
        lines = ["Memory:"]
        lines.extend(f"- [{memory.get('type', '')}] {memory.get('content', '')}" for memory in memories)
        ctx.base_model_context.memory_context = "\n".join(lines)


class ToolsSnapshotAvailableTools(Step):
    """Snapshot available tools from ToolRegistry into ctx.base_model_context."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        super().__init__("tools.snapshot_available_tools", HookPhase.before_agent)
        self._registry = registry

    def run(self, ctx: RunContext) -> None:
        if ctx.base_model_context is None:
            return
        if self._registry is None:
            ctx.base_model_context.available_tools = []
        else:
            ctx.base_model_context.available_tools = self._registry.list_schemas()


class BudgetInitialize(Step):
    """Initialize budget state (max iterations, token limits)."""

    def __init__(
        self,
        max_iterations: int = 25,
        max_tokens: int = 200_000,
    ) -> None:
        super().__init__("budget.initialize", HookPhase.before_agent)
        self._max_iterations = max_iterations
        self._max_tokens = max_tokens

    def run(self, ctx: RunContext) -> None:
        ctx.budget = BudgetState(
            max_iterations=self._max_iterations,
            max_tokens=self._max_tokens,
        )


class RunCreate(Step):
    """Write AgentRun record to TimelineStore (status=running)."""

    def __init__(self) -> None:
        super().__init__("run.create", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        run = AgentRun(run_id=ctx.run_id, session_id=ctx.session_id, branch_id=ctx.branch_id)
        store.create_run(run)


class MessageCommitUser(Step):
    """Persist user input as role=user message to branch timeline."""

    def __init__(self) -> None:
        super().__init__("message.commit_user", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        seq = store.get_latest_sequence(ctx.branch_id) + 1
        msg = Message(
            message_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            sequence=seq,
            role="user",
            content=ctx.input,
        )
        store.append_message(msg)


class BranchResolveActive(Step):
    """Load active branch from session and set ctx.branch_id."""

    def __init__(self) -> None:
        super().__init__("branch.resolve_active", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        if ctx.branch_id:
            return
        session = store.get_session(ctx.session_id)
        if session is None:
            return
        ctx.branch_id = session.active_branch_id


class CheckpointCreateUserSnapshot(Step):
    """Create user_snapshot checkpoint after committing user message."""

    def __init__(self) -> None:
        super().__init__("checkpoint.create_user_snapshot", HookPhase.before_agent)

    def run(self, ctx: RunContext) -> None:
        store = ctx.timeline_store
        if store is None:
            return
        cursor = store.get_latest_sequence(ctx.branch_id)
        cp = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            kind=CheckpointKind.user_snapshot,
            name="user_message_committed",
            message_cursor=cursor,
        )
        store.create_checkpoint(cp)
