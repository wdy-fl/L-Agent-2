"""Factory: assemble a fully-wired AgentRunner ready for production use."""

from __future__ import annotations

from pathlib import Path

from agent.actions.model_call import make_llm_call_action, make_llm_stream_action
from agent.actions.tool_call import make_tool_call_action
from agent.config.settings import load_settings
from agent.context.compressor import ContextCompressor
from agent.core.runner import AgentRunner
from agent.llm.client import OpenAICompatibleClient
from agent.llm.types import ModelConfig
from agent.middleware.chain import MiddlewareChain
from agent.middleware.model import BudgetGuard, TraceRecord
from agent.middleware.tool import ApprovalGuard, AuditRecord, ResultLimitGuard
from agent.steps.after_agent import AgentHomeRunFinalize
from agent.steps.after_model import (
    MessageCommitAssistant,
    ModelCaptureResponse,
    ResultDetectFinalAnswer,
    ToolDetectRequested,
    UsageUpdate,
)
from agent.steps.after_tool import MessageCommitToolResults, ToolResultsCapture
from agent.steps.before_agent import (
    BudgetInitialize,
    CheckpointCreateUserSnapshot,
    ContextInitialize,
    MemoryPrefetch,
    MessageCommitUser,
    RunCreate,
    ToolsSnapshotAvailableTools,
)
from agent.steps.before_model import (
    ContextPrepareWithBudget,
    IterationCreate,
    ModelRequestCompose,
)
from agent.steps.before_tool import (
    ApprovalPrepareRequests,
    ToolCallsExtract,
    ToolCallsParseArguments,
    ToolCallsResolveTools,
    ToolCallsValidateSchema,
    ToolPlanBuildSerial,
)
from agent.steps.registry import StepRegistry
from agent.tools.builtin import create_builtin_registry
from agent.tools.dispatcher import ToolDispatcher


def build_runner(config_path: Path | None = None, home_client=None) -> AgentRunner:
    settings = load_settings(config_path)

    if not settings.llm.api_key:
        raise RuntimeError(
            "llm.api_key is required. Set it in workspace/config.yaml or ~/.l-agent/config.yaml"
        )

    model_config = ModelConfig(
        model=settings.llm.model,
        api_base=settings.llm.api_base,
        api_key=settings.llm.api_key,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )
    client = OpenAICompatibleClient(api_base=settings.llm.api_base, api_key=settings.llm.api_key)

    tool_registry = create_builtin_registry(home_client=home_client)
    dispatcher = ToolDispatcher(tool_registry)

    reg = StepRegistry()
    reg.register(RunCreate())
    reg.register(ContextInitialize(
        agent_file_path=settings.agent.agent_file_path,
        model_config=model_config,
    ))
    reg.register(MemoryPrefetch(limit=settings.agent_home.memory_prefetch_limit))
    reg.register(MessageCommitUser())
    reg.register(CheckpointCreateUserSnapshot())
    reg.register(ToolsSnapshotAvailableTools(registry=tool_registry))
    reg.register(BudgetInitialize(
        max_iterations=settings.budget.max_iterations,
        max_tokens=settings.budget.max_tokens,
    ))

    reg.register(IterationCreate())

    chain = MiddlewareChain()
    chain.add(BudgetGuard())
    chain.add(TraceRecord())
    chain.add(ApprovalGuard())
    chain.add(AuditRecord())
    chain.add(ResultLimitGuard())

    model_action = make_llm_call_action(client)

    compressor = ContextCompressor(
        context_window=settings.context.max_context_tokens,
        threshold=settings.context.compression_threshold,
        protected_head=settings.context.protected_head,
        protected_tail_tokens=settings.context.protected_tail_tokens,
        min_saving=settings.context.min_saving,
    )
    reg.register(ContextPrepareWithBudget(
        compressor=compressor,
        max_context_tokens=settings.context.max_context_tokens,
        middleware_chain=chain,
        model_action=model_action,
    ))
    reg.register(ModelRequestCompose())

    reg.register(ModelCaptureResponse())
    reg.register(MessageCommitAssistant())
    reg.register(UsageUpdate())
    reg.register(ResultDetectFinalAnswer())
    reg.register(ToolDetectRequested())

    reg.register(ToolCallsExtract())
    reg.register(ToolCallsParseArguments())
    reg.register(ToolCallsValidateSchema())
    reg.register(ToolCallsResolveTools())
    reg.register(ToolPlanBuildSerial())
    reg.register(ApprovalPrepareRequests())

    reg.register(ToolResultsCapture())
    reg.register(MessageCommitToolResults())

    reg.register(AgentHomeRunFinalize(auto_extract_memory=settings.agent_home.auto_extract_memory))

    return AgentRunner(
        registry=reg,
        middleware_chain=chain,
        model_call=model_action,
        tool_call=make_tool_call_action(dispatcher),
        model_stream=make_llm_stream_action(client),
    )
