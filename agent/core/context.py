from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent.llm.types import ModelConfig, ModelRequest, ModelResponse

if TYPE_CHECKING:
    from agent.timeline.store import TimelineStore


@dataclass
class BudgetState:
    """Tracks budget consumption for the current run."""

    max_iterations: int = 25
    max_tokens: int = 200_000
    consumed_iterations: int = 0
    consumed_input_tokens: int = 0
    consumed_output_tokens: int = 0
    exhausted: bool = False

    @property
    def consumed_total_tokens(self) -> int:
        return self.consumed_input_tokens + self.consumed_output_tokens


@dataclass
class RunContext:
    """Mutable blackboard for a single AgentRun."""

    # --- basic ---
    session_id: str = ""
    branch_id: str = ""
    run_id: str = ""
    input: str = ""
    raw_input: str = ""
    enhanced_input: str = ""
    iteration_index: int = 0
    iterations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    interrupted: bool = False

    # --- messages ---
    messages: list[dict[str, Any]] = field(default_factory=list)

    # --- model request state ---
    model_config: ModelConfig = field(default_factory=ModelConfig)
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    current_model_request: ModelRequest | None = None
    current_model_response: ModelResponse | None = None

    # --- tool ---
    current_tool_plan: Any = None
    current_tool_results: Any = None
    has_tool_calls: bool = False
    auto_approve_tools: set[str] = field(default_factory=set)
    always_confirm_tools: set[str] = field(default_factory=set)

    # --- budget ---
    budget: BudgetState = field(default_factory=BudgetState)

    # --- result ---
    final_result: Any = None
    status: str = "running"

    # --- timeline store ---
    timeline_store: TimelineStore | None = None
    home_client: Any = None
