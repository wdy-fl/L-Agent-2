from __future__ import annotations

import json
from typing import Any

from agent.core.context import RunContext
from agent.core.lifecycle import HookPhase
from agent.llm.types import ModelResponse
from agent.steps.base import Step
from agent.tools.base import ToolCall, ToolPlan


class ToolCallsExtract(Step):
    """Extract tool_calls list from ctx.current_model_response."""

    def __init__(self) -> None:
        super().__init__("tool_calls.extract", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        resp = ctx.current_model_response
        if resp is None or not isinstance(resp, ModelResponse):
            return

        calls: list[ToolCall] = []
        for tc in resp.tool_calls:
            calls.append(ToolCall(
                call_id=tc.id,
                tool_name=tc.name,
                arguments={},
            ))

        ctx.current_tool_plan = ToolPlan(calls=calls)


class ToolCallsParseArguments(Step):
    """Parse JSON string arguments into dict; mark parse failures as error."""

    def __init__(self) -> None:
        super().__init__("tool_calls.parse_arguments", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        resp = ctx.current_model_response
        if resp is None or not isinstance(resp, ModelResponse):
            return

        plan: ToolPlan | None = ctx.current_tool_plan
        if plan is None:
            return

        for i, call in enumerate(plan.calls):
            raw_args = resp.tool_calls[i].arguments
            if not raw_args or raw_args.strip() == "":
                call.arguments = {}
                continue
            try:
                parsed = json.loads(raw_args)
                if not isinstance(parsed, dict):
                    call.error = f"Arguments must be a JSON object, got {type(parsed).__name__}"
                    continue
                call.arguments = parsed
            except json.JSONDecodeError as exc:
                call.error = f"Failed to parse arguments: {exc}"


class ToolCallsValidateSchema(Step):
    """Validate parsed arguments against tool's parameters_schema."""

    def __init__(self) -> None:
        super().__init__("tool_calls.validate_schema", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        plan: ToolPlan | None = ctx.current_tool_plan
        if plan is None:
            return

        available_tools = self._get_available_tools(ctx)

        for call in plan.calls:
            if call.error:
                continue

            spec = available_tools.get(call.tool_name)
            if spec is None:
                continue

            schema = spec.get("parameters", {})
            required = schema.get("required", [])
            properties = schema.get("properties", {})

            for param_name in required:
                if param_name not in call.arguments:
                    call.error = f"Missing required parameter: {param_name}"
                    break

            if call.error:
                continue

            for param_name in call.arguments:
                if properties and param_name not in properties:
                    call.error = f"Unknown parameter: {param_name}"
                    break

    def _get_available_tools(self, ctx: RunContext) -> dict[str, Any]:
        tools_map: dict[str, Any] = {}
        for tool_schema in ctx.available_tools:
            func_def = tool_schema.get("function", {})
            name = func_def.get("name", "")
            if name:
                tools_map[name] = func_def
        return tools_map


class ToolCallsResolveTools(Step):
    """Confirm each tool exists in the available_tools snapshot."""

    def __init__(self) -> None:
        super().__init__("tool_calls.resolve_tools", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        plan: ToolPlan | None = ctx.current_tool_plan
        if plan is None:
            return

        available_names = self._get_available_tool_names(ctx)

        for call in plan.calls:
            if call.error:
                continue
            if call.tool_name not in available_names:
                call.error = f"Tool not available: {call.tool_name}"

    def _get_available_tool_names(self, ctx: RunContext) -> set[str]:
        names: set[str] = set()
        for tool_schema in ctx.available_tools:
            func_def = tool_schema.get("function", {})
            name = func_def.get("name", "")
            if name:
                names.add(name)
        return names


class ToolPlanBuildSerial(Step):
    """Build serial execution plan preserving model's call order."""

    def __init__(self) -> None:
        super().__init__("tool_plan.build_serial", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        plan: ToolPlan | None = ctx.current_tool_plan
        if plan is None:
            return
        plan.execution_mode = "serial"


class ApprovalPrepareRequests(Step):
    """Identify which calls need approval (first version: mark only, no blocking)."""

    def __init__(self) -> None:
        super().__init__("approval.prepare_requests", HookPhase.before_tool)

    def run(self, ctx: RunContext) -> None:
        pass
