"""Factory: assemble a fully-wired AgentRunner ready for production use."""

from __future__ import annotations

from pathlib import Path

from agent.actions.model_call import make_llm_call_action
from agent.actions.tool_call import make_tool_call_action
from agent.config.settings import Settings, load_settings
from agent.core.runner import AgentRunner
from agent.llm.client import OpenAICompatibleClient
from agent.llm.types import ModelConfig
from agent.middleware.chain import MiddlewareChain
from agent.middleware.model import BudgetGuard, TraceRecord
from agent.middleware.tool import ApprovalGuard, AuditRecord, ResultLimitGuard
from agent.steps.after_model import (
    MessageCommitAssistant,
    ModelCaptureResponse,
    ResultDetectFinalAnswer,
    ToolDetectRequested,
    UsageUpdate,
)
from agent.steps.after_tool import MessageCommitToolResults, ToolResultsCapture
from agent.steps.before_agent import (
    BaseContextLoadStaticParts,
    BudgetInitialize,
    ContextInitialize,
    InputNormalize,
    MemoryPrefetch,
    ToolsSnapshotAvailableTools,
)
from agent.steps.before_model import (
    ContextPrepareWithBudget,
    IterationCreate,
    MessagesCollectVisible,
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


def build_runner(config_path: Path | None = None) -> AgentRunner:
    settings = load_settings(config_path)

    if not settings.llm.api_key:
        raise RuntimeError(
            "llm.api_key is required. Set it in .l-agent/config.yaml or ~/.l-agent/config.yaml"
        )

    model_config = ModelConfig(
        model=settings.llm.model,
        api_base=settings.llm.api_base,
        api_key=settings.llm.api_key,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )
    client = OpenAICompatibleClient(api_base=settings.llm.api_base, api_key=settings.llm.api_key)

    tool_registry = create_builtin_registry()
    dispatcher = ToolDispatcher(tool_registry)

    reg = StepRegistry()
    reg.register(ContextInitialize())
    reg.register(InputNormalize())
    reg.register(BaseContextLoadStaticParts(
        identity=settings.agent.identity,
        guidance=settings.agent.guidance,
        model_config=model_config,
    ))
    reg.register(MemoryPrefetch())
    reg.register(ToolsSnapshotAvailableTools(registry=tool_registry))
    reg.register(BudgetInitialize(
        max_iterations=settings.budget.max_iterations,
        max_tokens=settings.budget.max_tokens,
    ))

    reg.register(IterationCreate())
    reg.register(MessagesCollectVisible())
    reg.register(ContextPrepareWithBudget())
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

    chain = MiddlewareChain()
    chain.add(BudgetGuard())
    chain.add(TraceRecord())
    chain.add(ApprovalGuard())
    chain.add(AuditRecord())
    chain.add(ResultLimitGuard())

    return AgentRunner(
        registry=reg,
        middleware_chain=chain,
        model_call=make_llm_call_action(client),
        tool_call=make_tool_call_action(dispatcher),
    )
