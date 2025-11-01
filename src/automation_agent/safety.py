"""Prompt safety heuristics and guardrails.

The module implements a lightweight, easily extensible layer inspired by
"safeguard" releases for modern LLM ecosystems.  It provides a rule based
prompt inspector that can be configured from ``automation_config.yml`` or used
programmatically when constructing :class:`AutomationAgent` instances.  The
implementation is deliberately dependency free so it can run in constrained
automation environments.
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

from .config import RemoteGuardConfig


Severity = str


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyFinding:
    """Represents a single issue flagged by the safety engine."""

    rule: str
    message: str
    severity: Severity = "medium"
    remediation: Optional[str] = None
    tags: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity,
            "remediation": self.remediation,
            "tags": list(self.tags),
        }


@dataclass
class SafetyReport:
    """Result returned after inspecting a prompt."""

    findings: List[SafetyFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings

    def summary(self) -> str:
        if self.passed:
            return "No safety findings"
        parts = [
            f"[{finding.severity}] {finding.rule}: {finding.message}"
            for finding in self.findings
        ]
        return "; ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass
class PromptSafetyRule:
    """Regular-expression based rule for detecting unsafe prompts."""

    name: str
    pattern: Pattern[str]
    description: str
    severity: Severity = "medium"
    remediation: Optional[str] = None
    tags: Tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PromptSafetyRule":
        pattern = payload.get("pattern")
        if not pattern:
            raise ValueError("Safety rule requires a 'pattern' field")
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        return cls(
            name=payload.get("name", pattern),
            pattern=compiled,
            description=payload.get("description", pattern),
            severity=payload.get("severity", "medium"),
            remediation=payload.get("remediation"),
            tags=tuple(payload.get("tags", ())),
        )


@dataclass
class PromptSafetyEngine:
    """Evaluate prompts against a configurable set of rules."""

    rules: List[PromptSafetyRule] = field(default_factory=list)

    def add_rule(self, rule: PromptSafetyRule) -> None:
        self.rules.append(rule)

    def extend(self, rules: Iterable[PromptSafetyRule]) -> None:
        for rule in rules:
            self.add_rule(rule)

    def inspect(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> SafetyReport:
        """Return a :class:`SafetyReport` for the supplied prompt/context."""

        surfaces: List[str] = [prompt]
        if context:
            try:
                surfaces.append(json.dumps(context, default=str))
            except TypeError:
                # Fallback when context contains non-serialisable objects.
                surfaces.append(str(context))
        corpus = "\n".join(surfaces)
        findings: List[SafetyFinding] = []
        for rule in self.rules:
            if rule.pattern.search(corpus):
                findings.append(
                    SafetyFinding(
                        rule=rule.name,
                        message=rule.description,
                        severity=rule.severity,
                        remediation=rule.remediation,
                        tags=rule.tags,
                    )
        )
        return SafetyReport(findings=findings)

    @classmethod
    def default(cls) -> "PromptSafetyEngine":
        """Construct a guard with opinionated defaults."""

        engine = cls()
        engine.extend(
            [
                PromptSafetyRule(
                    name="prompt_injection_ignore_instructions",
                    pattern=re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
                    description="Request attempts to override system instructions.",
                    severity="high",
                    remediation="Rephrase the prompt without overriding safeguards.",
                    tags=("prompt-injection",),
                ),
                PromptSafetyRule(
                    name="credentials_exfiltration",
                    pattern=re.compile(r"(api[_-]?key|password|secret|token)", re.IGNORECASE),
                    description="Prompt references credential exfiltration.",
                    severity="high",
                    remediation="Remove references to secrets or credentials.",
                    tags=("data-protection",),
                ),
                PromptSafetyRule(
                    name="destructive_shell_command",
                    pattern=re.compile(r"rm\s+-rf|del\s+/s|shutdown\s+-h", re.IGNORECASE),
                    description="Prompt contains potentially destructive shell commands.",
                    severity="high",
                    remediation="Avoid destructive shell operations in automated plans.",
                    tags=("destructive", "shell"),
                ),
                PromptSafetyRule(
                    name="sql_drop_statement",
                    pattern=re.compile(r"drop\s+(table|database)|truncate\s+table", re.IGNORECASE),
                    description="Prompt requests destructive SQL actions.",
                    severity="medium",
                    remediation="Use read-only SQL or confirm destructive intent manually.",
                    tags=("sql", "destructive"),
                ),
                PromptSafetyRule(
                    name="sensitive_metadata_access",
                    pattern=re.compile(r"(system\s+prompt|model\s+weights|training\s+data)", re.IGNORECASE),
                    description="Prompt asks for internal system details.",
                    severity="medium",
                    remediation="Do not expose internal system metadata to end users.",
                    tags=("data-protection", "metadata"),
                ),
            ]
        )
        return engine


class RemoteGuardError(RuntimeError):
    """Raised when the remote guard cannot process a request."""


@dataclass
class RemoteGuardClient:
    """Client wrapper that queries a remote guard service."""

    config: RemoteGuardConfig

    def inspect(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> SafetyReport:
        payload = {"prompt": prompt, "context": context or {}}
        data = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(self.config.endpoint, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.config.api_key:
            request.add_header("Authorization", f"Bearer {self.config.api_key}")
        for header, value in (self.config.headers or {}).items():
            request.add_header(header, value)
        try:
            with urllib_request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib_error.URLError as exc:  # pragma: no cover - network failure path
            raise RemoteGuardError(f"Remote guard request failed: {exc}") from exc
        if not body:
            return SafetyReport()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RemoteGuardError("Remote guard returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteGuardError("Remote guard response must be a JSON object")
        findings_payload = []
        if not payload.get("passed", True):
            findings_payload = payload.get("findings") or []
        findings: List[SafetyFinding] = []
        for raw in findings_payload:
            if not isinstance(raw, dict):
                continue
            findings.append(
                SafetyFinding(
                    rule=str(raw.get("rule", "remote_guard")),
                    message=str(raw.get("message", "Remote guard flagged the prompt.")),
                    severity=str(raw.get("severity", "medium")),
                    remediation=raw.get("remediation"),
                    tags=tuple(raw.get("tags", ())),
                )
            )
        return SafetyReport(findings=findings)


@dataclass
class SafetyCoordinator:
    """Combine local safety rules with optional remote guard results."""

    local_engine: PromptSafetyEngine | None = None
    remote_guard: RemoteGuardClient | None = None

    def inspect(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> SafetyReport:
        findings: List[SafetyFinding] = []
        if self.remote_guard:
            try:
                remote_report = self.remote_guard.inspect(prompt, context=context)
                findings.extend(remote_report.findings)
            except RemoteGuardError as exc:
                LOGGER.warning("Remote guard unavailable: %s", exc)
        if self.local_engine:
            local_report = self.local_engine.inspect(prompt, context=context)
            findings.extend(local_report.findings)
        return SafetyReport(findings=findings)


__all__ = [
    "PromptSafetyEngine",
    "PromptSafetyRule",
    "SafetyFinding",
    "SafetyReport",
    "SafetyCoordinator",
    "RemoteGuardClient",
    "RemoteGuardError",
]

