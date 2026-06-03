from enum import Enum


class HookPhase(str, Enum):
    before_agent = "before_agent"
    before_model = "before_model"
    after_model = "after_model"
    before_tool = "before_tool"
    after_tool = "after_tool"
    after_agent = "after_agent"

    @property
    def is_run_level(self) -> bool:
        return self in (HookPhase.before_agent, HookPhase.after_agent)

    @property
    def is_iteration_level(self) -> bool:
        return not self.is_run_level


class ActionName(str, Enum):
    model_call = "model_call"
    tool_call = "tool_call"
