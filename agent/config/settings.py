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
class ContextSettings:
    max_context_tokens: int = 128_000
    compression_threshold: float = 0.5
    protected_head: int = 3
    protected_tail_tokens: int = 20_000
    min_saving: float = 0.1


@dataclass
class BudgetSettings:
    max_iterations: int = 25
    max_tokens: int = 200_000


@dataclass
class AgentSettings:
    agent_file_path: str = ""


@dataclass
class AgentHomeSettings:
    base_url: str = "http://127.0.0.1:8765"
    agent_id: str = ""
    token: str = ""
    auto_create_agent: bool = True
    auto_extract_memory: bool = False
    memory_prefetch_limit: int = 5


@dataclass
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    agent_home: AgentHomeSettings = field(default_factory=AgentHomeSettings)
    config_dir: Path = field(default_factory=lambda: Path("."))


DEFAULT_CONFIG_PATHS = [
    Path("workspace/config.yaml"),
    Path.home() / ".l-agent" / "config.yaml",
]


def load_settings(config_path: Path | None = None) -> Settings:
    path = _resolve_path(config_path)
    if path is None:
        settings = Settings()
        _require_agent_id(settings)
        return settings

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    settings = _parse(data)
    settings.config_dir = path.parent
    _require_agent_id(settings)
    return settings


def _resolve_path(config_path: Path | None) -> Path | None:
    if config_path and config_path.exists():
        return config_path
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _require_agent_id(settings: Settings) -> None:
    if not settings.agent_home.agent_id:
        raise RuntimeError("agent_home.agent_id is required. Set it in workspace/config.yaml or ~/.l-agent/config.yaml")


def _parse(data: dict[str, Any]) -> Settings:
    llm_data = data.get("llm", {})
    budget_data = data.get("budget", {})
    context_data = data.get("context", {})
    agent_data = data.get("agent", {})
    home_data = data.get("agent_home", {})

    return Settings(
        llm=LLMSettings(**{k: v for k, v in llm_data.items() if k in LLMSettings.__dataclass_fields__}),
        budget=BudgetSettings(**{k: v for k, v in budget_data.items() if k in BudgetSettings.__dataclass_fields__}),
        context=ContextSettings(**{k: v for k, v in context_data.items() if k in ContextSettings.__dataclass_fields__}),
        agent=AgentSettings(**{k: v for k, v in agent_data.items() if k in AgentSettings.__dataclass_fields__}),
        agent_home=AgentHomeSettings(**{k: v for k, v in home_data.items() if k in AgentHomeSettings.__dataclass_fields__}),
    )


def write_agent_home_credentials(config_path: Path, token: str) -> None:
    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    data.setdefault("agent_home", {})
    data["agent_home"]["token"] = token
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
