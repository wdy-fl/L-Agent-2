"""Application settings loaded from YAML config file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMSettings:
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class BudgetSettings:
    max_iterations: int = 25
    max_tokens: int = 200_000


@dataclass
class AgentSettings:
    identity: str = "You are L-Agent, an AI coding assistant. Use the available tools to help the user."
    guidance: str = "Be concise. Think step by step. Use tools when needed."


@dataclass
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)


DEFAULT_CONFIG_PATHS = [
    Path("workspace/config.yaml"),
    Path.home() / ".l-agent" / "config.yaml",
]


def load_settings(config_path: Path | None = None) -> Settings:
    path = _resolve_path(config_path)
    if path is None:
        return Settings()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return _parse(data)


def _resolve_path(config_path: Path | None) -> Path | None:
    if config_path and config_path.exists():
        return config_path
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _parse(data: dict[str, Any]) -> Settings:
    llm_data = data.get("llm", {})
    budget_data = data.get("budget", {})
    agent_data = data.get("agent", {})

    return Settings(
        llm=LLMSettings(**{k: v for k, v in llm_data.items() if k in LLMSettings.__dataclass_fields__}),
        budget=BudgetSettings(**{k: v for k, v in budget_data.items() if k in BudgetSettings.__dataclass_fields__}),
        agent=AgentSettings(**{k: v for k, v in agent_data.items() if k in AgentSettings.__dataclass_fields__}),
    )
