from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    """Mutable blackboard for a single AgentRun."""

    # --- basic ---
    session_id: str = ""
    branch_id: str = ""
    run_id: str = ""
    input: str = ""
    iterations: int = 0
    errors: list[Exception] = field(default_factory=list)
    interrupted: bool = False

    # --- model placeholders ---
    base_model_context: Any = None
    current_model_request: Any = None
    current_model_response: Any = None

    # --- tool placeholders ---
    current_tool_plan: Any = None
    current_tool_results: Any = None

    # --- result ---
    final_result: Any = None
    has_tool_calls: bool = False
