"""Configuration helpers for the automation agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# PyYAML is optional; fall back to JSON-only mode if unavailable.
try:  # pragma: no cover - import guard
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


@dataclass
class ProviderConfig:
    """Configuration for a language model provider."""

    name: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    options: Dict[str, Any] | None = None


@dataclass
class AutomationConfig:
    """Top level configuration for the automation runtime."""

    provider: ProviderConfig
    tools: Dict[str, Dict[str, Any]] | None = None
    max_steps: int = 10

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AutomationConfig":
        provider = ProviderConfig(**payload.get("provider", {}))
        return cls(
            provider=provider,
            tools=payload.get("tools"),
            max_steps=int(payload.get("max_steps", 10)),
        )


def load_config(path: str | Path) -> AutomationConfig:
    """Load configuration from JSON or YAML."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".json"}:
        payload = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to load YAML configuration files. Install with 'pip install pyyaml'."
            )
        payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise ValueError("Configuration must define a mapping")
    return AutomationConfig.from_dict(payload)
