"""Tests for AgentRunner: tool_calls branching, exceptions, and interrupts."""

from agent.core.context import RunContext
from agent.core.lifecycle import HookPhase
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


class TestToolCallsBranching:
    def test_has_tool_calls_true_enters_tool_phase(self):
        """When has_tool_calls is True, before_tool/tool_call/after_tool execute."""
        log: list[str] = []
        reg = StepRegistry()
        reg.register(RecordingStep("bt", HookPhase.before_tool, log))
        reg.register(RecordingStep("at", HookPhase.after_tool, log))

        call_count = [0]

        def model_call(ctx: RunContext):
            call_count[0] += 1
            if call_count[0] == 1:
                ctx.has_tool_calls = True
            else:
                ctx.final_result = "done"
            return None

        def tool_call(ctx: RunContext):
            log.append("tool_executed")
            return None

        runner = _make_runner(reg, model_call=model_call, tool_call=tool_call)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert "before_tool:bt" in log
        assert "tool_executed" in log
        assert "after_tool:at" in log

    def test_has_tool_calls_false_skips_tool_phase(self):
        """When has_tool_calls is False, tool phases never execute."""
        log: list[str] = []
        reg = StepRegistry()
        reg.register(RecordingStep("bt", HookPhase.before_tool, log))
        reg.register(RecordingStep("at", HookPhase.after_tool, log))

        def model_call(ctx: RunContext):
            ctx.final_result = "done"
            return None

        runner = _make_runner(reg, model_call=model_call)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert "before_tool:bt" not in log
        assert "after_tool:at" not in log


class TestExceptionHandling:
    def test_exception_in_model_call_enters_after_agent(self):
        """If model_call raises, after_agent still runs."""
        log: list[str] = []
        reg = StepRegistry()
        reg.register(RecordingStep("aa", HookPhase.after_agent, log))

        def model_call(ctx: RunContext):
            raise RuntimeError("model failed")

        runner = _make_runner(reg, model_call=model_call)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert "after_agent:aa" in log
        assert len(ctx.errors) == 1
        assert "model failed" in str(ctx.errors[0])

    def test_exception_in_step_enters_after_agent(self):
        """If a step raises, after_agent still runs."""
        log: list[str] = []
        reg = StepRegistry()

        class FailingStep(Step):
            def run(self, ctx: RunContext) -> None:
                raise ValueError("step failed")

        reg.register(FailingStep("bad", HookPhase.before_model))
        reg.register(RecordingStep("aa", HookPhase.after_agent, log))

        runner = _make_runner(reg)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert "after_agent:aa" in log
        assert len(ctx.errors) == 1
        assert "step failed" in str(ctx.errors[0])

    def test_interrupted_exits_loop(self):
        """Setting interrupted=True should stop the ReAct loop."""
        log: list[str] = []
        reg = StepRegistry()
        reg.register(RecordingStep("aa", HookPhase.after_agent, log))

        call_count = [0]

        def model_call(ctx: RunContext):
            call_count[0] += 1
            ctx.has_tool_calls = True
            return None

        def tool_call(ctx: RunContext):
            ctx.interrupted = True
            return None

        runner = _make_runner(reg, model_call=model_call, tool_call=tool_call)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert call_count[0] == 1
        assert "after_agent:aa" in log

    def test_iterations_count(self):
        """iterations should increment once per loop iteration."""
        call_count = [0]

        def model_call(ctx: RunContext):
            call_count[0] += 1
            if call_count[0] < 3:
                ctx.has_tool_calls = True
            else:
                ctx.final_result = "done"
            return None

        runner = _make_runner(StepRegistry(), model_call=model_call, tool_call=lambda ctx: None)
        ctx = RunContext(input="test")
        runner.run(ctx)

        assert ctx.iterations == 3
