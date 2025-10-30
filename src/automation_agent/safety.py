"""Safety utilities for prompts and plan validation."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

LOGGER = logging.getLogger(__name__)


class SafetyViolationError(RuntimeError):
    """Raised when a prompt or plan violates configured safety policies."""


@dataclass
class SafetyChecker:
    """Evaluate prompts and plan steps against guardrails."""

    blocked_terms: Iterable[str] | None = None
    guard_url: Optional[str] = None
    api_key: Optional[str] = None
    options: Dict[str, object] | None = None
    request_timeout: float = 10.0

    def check_prompt(self, prompt: str, *, context: Optional[Dict[str, object]] = None) -> None:
        """Validate an incoming prompt before it is sent to a model."""

        parts = [prompt]
        if context:
            parts.append(json.dumps(context, sort_keys=True))
        self._evaluate_text("prompt", "\n".join(parts))

    def check_plan(self, steps: Iterable[object]) -> None:
        """Validate the generated plan before execution."""

        serialized = []
        for step in steps:
            try:
                tool = getattr(step, "tool", "unknown")
                description = getattr(step, "description", "")
            except Exception:  # pragma: no cover - defensive
                continue
            serialized.append(f"{tool}: {description}")
        if serialized:
            self._evaluate_text("plan", "\n".join(serialized))

    # ------------------------------------------------------------------
    # Internal helpers
    def _evaluate_text(self, label: str, text: str) -> None:
        self._enforce_blocked_terms(label, text)
        self._call_guard_service(label, text)

    def _enforce_blocked_terms(self, label: str, text: str) -> None:
        if not self.blocked_terms:
            return
        lowered = text.lower()
        for term in self.blocked_terms:
            if term.lower() in lowered:
                raise SafetyViolationError(
                    f"Safety policy rejected {label}: contains disallowed term '{term}'"
                )

    def _call_guard_service(self, label: str, text: str) -> None:
        if not self.guard_url:
            return
        payload = {
            "label": label,
            "input": text,
        }
        if self.options:
            payload.update(self.options)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.guard_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:  # pragma: no cover - depends on network
            LOGGER.warning("Safety guard service unavailable: %s", exc)
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - depends on service response
            LOGGER.warning("Invalid response from safety guard: %s", raw)
            return
        allowed = parsed.get("allowed")
        if allowed is False:
            reason = parsed.get("reason", "Rejected by guard service")
            raise SafetyViolationError(f"Safety guard rejected {label}: {reason}")


__all__ = ["SafetyChecker", "SafetyViolationError"]

