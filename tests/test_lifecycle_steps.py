"""Tests for phase execution order and step registry."""

from agent.core.context import RunContext
from agent.core.lifecycle import ActionName, HookPhase
from agent.core.runner import AgentRunner
from agent.middleware.chain import MiddlewareChain
from agent.steps.base import Step
from agent.steps.registry import StepRegistry


class RecordingStep(Step):
    def __init__(self, name: str, phase: HookPhase, log: list[str]) -> None:
        super().__init__(name, phase)
        self._log = log

    def run(self, ctx: RunContext) -> None:
        self._log.append(f"{self.phase.value}:{self.name}")


def _make_runner(registry: StepRegistry, model_call=None, tool_call=None):
    return AgentRunner(
        registry=registry,
        middleware_chain=MiddlewareChain(),
        model_call=model_call,
        tool_call=tool_call,
    )


class TestPhaseExecutionOrder:
    def test_no_tool_calls_phase_order(self):
        """Without tool_calls, should skip before_tool/tool_call/after_tool."""
        log: list[str] = []
        reg = StepRegistry()
        for phase in HookPhase:
            reg.register(RecordingStep(f"s_{phase.value}", phase, log))

        def model_call(ctx: RunContext):
            log.append("action:model_call")
            ctx.final_result = "done"
            return "done"

        runner = _make_runner(reg, model_call=model_call)
        ctx = RunContext(input="hello")
        runner.run(ctx)

        assert log == [
            "before_agent:s_before_agent",
            "before_model:s_before_model",
            "action:model_call",
            "after_model:s_after_model",
            "after_agent:s_after_agent",
        ]

    def test_with_tool_calls_phase_order(self):
        """With tool_calls, should execute full cycle then loop back."""
        log: list[str] = []
        reg = StepRegistry()
        for phase in HookPhase:
            reg.register(RecordingStep(f"s_{phase.value}", phase, log))

        call_count = [0]

        def model_call(ctx: RunContext):
            call_count[0] += 1
            log.append(f"action:model_call:{call_count[0]}")
            if call_count[0] == 1:
                ctx.has_tool_calls = True
                return "need_tools"
            ctx.final_result = "done"
            return "done"

        def tool_call(ctx: RunContext):
            log.append("action:tool_call")
            return "tool_result"

        runner = _make_runner(reg, model_call=model_call, tool_call=tool_call)
        ctx = RunContext(input="hello")
        runner.run(ctx)

        assert log == [
            "before_agent:s_before_agent",
            # iteration 1
            "before_model:s_before_model",
            "action:model_call:1",
            "after_model:s_after_model",
            "before_tool:s_before_tool",
            "action:tool_call",
            "after_tool:s_after_tool",
            # iteration 2
            "before_model:s_before_model",
            "action:model_call:2",
            "after_model:s_after_model",
            # no tool calls -> exit loop
            "after_agent:s_after_agent",
        ]

    def test_step_priority_order(self):
        """Steps within a phase should execute in priority order."""
        log: list[str] = []
        reg = StepRegistry()
        from agent.steps.registry import StepConfig

        reg.register(
            RecordingStep("high", HookPhase.before_agent, log),
            StepConfig(priority=10),
        )
        reg.register(
            RecordingStep("low", HookPhase.before_agent, log),
            StepConfig(priority=50),
        )
        reg.register(
            RecordingStep("mid", HookPhase.before_agent, log),
            StepConfig(priority=30),
        )

        runner = _make_runner(reg)
        ctx = RunContext(input="test")
        runner.run(ctx)

        before_agent_entries = [e for e in log if e.startswith("before_agent")]
        assert before_agent_entries == [
            "before_agent:high",
            "before_agent:mid",
            "before_agent:low",
        ]

    def test_disabled_step_skipped(self):
        """Disabled steps should not execute."""
        log: list[str] = []
        reg = StepRegistry()
        reg.register(RecordingStep("active", HookPhase.before_agent, log))
        reg.register(RecordingStep("disabled", HookPhase.before_agent, log))
        reg.configure("disabled", enabled=False)

        runner = _make_runner(reg)
        ctx = RunContext(input="test")
        runner.run(ctx)

        before_agent_entries = [e for e in log if e.startswith("before_agent")]
        assert before_agent_entries == ["before_agent:active"]
