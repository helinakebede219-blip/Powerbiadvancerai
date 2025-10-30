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
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple


Severity = str


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


__all__ = [
    "PromptSafetyEngine",
    "PromptSafetyRule",
    "SafetyFinding",
    "SafetyReport",
]

