from __future__ import annotations

import uuid
from typing import Any, Callable, cast

from agent.core.context import BudgetState, RunContext
from agent.core.lifecycle import HookPhase
from agent.llm.types import ModelConfig
from agent.steps.base import Step
from agent.timeline.models import AgentRun, Checkpoint, CheckpointKind, Message
from agent.timeline.resume import resume
from agent.tools.registry import ToolRegistry


def _message_to_dict(message: Message) -> dict[str, Any]:
    data: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = message.tool_calls
    if message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    return data


class ContextInitialize(Step):
    """Create RunContext fields."""

    def __init__(
        self,
        guidance: str = "",
        model_config: ModelConfig | None = None,
        agent_file_path: str = "",
    ) -> None:
        super().__init__("context.initialize", HookPhase.before_agent)
        self._guidance: str = guidance
        self._model_config: ModelConfig = model_config or ModelConfig()
        self._agent_file_path: str = agent_file_path

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

        ctx.messages.append({"role": "system", "content": guidance})

        seq = ctx.timeline_store.get_latest_sequence(ctx.branch_id) + 1
        ctx.timeline_store.append_message(
            Message(
                message_id=str(uuid.uuid4()),
                session_id=ctx.session_id,
                branch_id=ctx.branch_id,
                run_id=ctx.run_id,
                sequence=seq,
                role="system",
                content=guidance,
            )
        )

    def _load_agent_file(self, ctx: RunContext) -> str:
        path = self._agent_file_path
        home_client = ctx.home_client
        workspace_get_text = getattr(home_client, "workspace_get_text", None)
        if not callable(workspace_get_text):
            raise RuntimeError(f"Failed to load agent file from Agent Home workspace: {path}")
        get_text = cast(Callable[[str], str], workspace_get_text)
        try:
            return get_text(path).strip()
        except Exception as exc:
            raise RuntimeError(f"Failed to load agent file from Agent Home workspace: {path}") from exc


class MemoryPrefetch(Step):
    """Prefetch matching memories into enhanced input."""

    def __init__(self, limit: int = 5) -> None:
        super().__init__("memory.prefetch", HookPhase.before_agent)
        self._limit = limit

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
        memory_lines = [f"- [{memory.get('type', '')}] {memory.get('content', '')}" for memory in memories]
        ctx.enhanced_input = (
            "<memory>\n"
            + "\n".join(memory_lines)
            + "\n</memory>\n\n<user>\n"
            + ctx.input
            + "\n</user>"
        )


class ToolsSnapshotAvailableTools(Step):
    """Snapshot available tools from ToolRegistry into ctx.available_tools."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        super().__init__("tools.snapshot_available_tools", HookPhase.before_agent)
        self._registry = registry

    def run(self, ctx: RunContext) -> None:
        if self._registry is None:
            ctx.available_tools = []
        else:
            ctx.available_tools = self._registry.list_schemas()


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
            raise RuntimeError("timeline_store is required")
        if not ctx.session_id:
            raise RuntimeError("session_id is required")
        if not ctx.branch_id:
            raise RuntimeError("branch_id is required")
        if not ctx.enhanced_input:
            raise RuntimeError("enhanced_input is required")

        ctx.messages.append({"role": "user", "content": ctx.enhanced_input})

        seq = store.get_latest_sequence(ctx.branch_id) + 1
        msg = Message(
            message_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            branch_id=ctx.branch_id,
            run_id=ctx.run_id,
            sequence=seq,
            role="user",
            content=ctx.enhanced_input,
        )
        store.append_message(msg)


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
