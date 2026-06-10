from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """Model configuration parameters."""

    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096
    api_base: str = ""
    api_key: str = ""


@dataclass
class ModelRequest:
    """Iteration-level dynamic request, rebuilt every before_model."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class ToolCallRequest:
    """A single tool call within a model response."""

    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class Usage:
    """Token usage for a single model call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ModelResponse:
    """Response from an LLM call."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = "stop"
