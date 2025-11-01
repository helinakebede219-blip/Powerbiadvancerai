"""Configuration helpers for the automation agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RemoteGuardConfig:
    """Configuration for optional remote safety guardrails."""

    endpoint: str
    api_key: Optional[str] = None
    headers: Dict[str, str] | None = None
    timeout: float = 10.0

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RemoteGuardConfig":
        endpoint = payload.get("endpoint")
        if not endpoint:
            raise ValueError("Remote guard configuration requires an 'endpoint'")
        headers = payload.get("headers")
        if headers is not None and not isinstance(headers, dict):
            raise ValueError("Remote guard 'headers' must be a mapping of HTTP headers")
        return cls(
            endpoint=str(endpoint),
            api_key=payload.get("api_key"),
            headers={str(k): str(v) for k, v in (headers or {}).items()},
            timeout=float(payload.get("timeout", 10.0)),
        )

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
    safety: "SafetyConfig" = field(default_factory=lambda: SafetyConfig(enabled=True))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AutomationConfig":
        provider = ProviderConfig(**payload.get("provider", {}))
        return cls(
            provider=provider,
            tools=payload.get("tools"),
            max_steps=int(payload.get("max_steps", 10)),
            safety=SafetyConfig.from_dict(payload.get("safety", {})),
        )


@dataclass
class SafetyConfig:
    """Configuration for the prompt safety engine."""

    enabled: bool = True
    rules: List[Dict[str, Any]] | None = None
    remote_guard: Optional[RemoteGuardConfig] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SafetyConfig":
        if not payload:
            return cls()
        remote_payload = payload.get("remote_guard")
        remote_guard = None
        if isinstance(remote_payload, dict) and remote_payload:
            try:
                remote_guard = RemoteGuardConfig.from_dict(remote_payload)
            except ValueError:
                remote_guard = None
        return cls(
            enabled=bool(payload.get("enabled", True)),
            rules=payload.get("rules"),
            remote_guard=remote_guard,
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
