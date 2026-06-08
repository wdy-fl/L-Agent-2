"""Auto-approve configuration loader (YAML)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ApprovalConfig:
    """Configuration for tool approval behavior."""

    auto_approve: list[str] = field(default_factory=lambda: ["think", "read_file", "list_directory"])
    always_confirm: list[str] = field(default_factory=lambda: ["terminal", "write_file"])


def load_approval_config(config_path: Path | None = None) -> ApprovalConfig:
    """Load approval config from YAML file or return defaults."""
    if config_path is None or not config_path.exists():
        return ApprovalConfig()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    approval_data = data.get("approval", {})
    defaults = ApprovalConfig()
    return ApprovalConfig(
        auto_approve=approval_data.get("auto_approve", defaults.auto_approve),
        always_confirm=approval_data.get("always_confirm", defaults.always_confirm),
    )
