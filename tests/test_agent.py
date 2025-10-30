from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from automation_agent.agent import AutomationAgent
from automation_agent.llm import LLMProvider
from automation_agent.safety import SafetyChecker, SafetyViolationError
from automation_agent.tooling import PythonCallableTool, ToolRegistry, register_builtin_tools


@dataclass
class DummyProvider(LLMProvider):
    response: str

    def generate(self, prompt: str, *, context=None) -> str:  # type: ignore[override]
        return self.response


def test_fallback_plan_when_invalid_json():
    provider = DummyProvider(response="not json")
    registry = register_builtin_tools()
    agent = AutomationAgent(provider=provider, registry=registry)
    steps = agent.plan_workflow("Please automate dataset refresh schedule")
    assert steps, "Fallback should produce at least one step"
    assert any(step.tool == "schedule_refresh" for step in steps)


def test_execute_skips_missing_tool():
    provider = DummyProvider(response=json.dumps({"steps": [{"tool": "unknown", "description": ""}]}))
    registry = register_builtin_tools()
    agent = AutomationAgent(provider=provider, registry=registry)
    steps = agent.plan_workflow("anything")
    results = agent.execute_workflow(steps)
    assert results[0].status == "skipped"


def test_custom_tool_execution():
    provider = DummyProvider(response=json.dumps({"steps": [{"tool": "echo", "description": "", "args": {"text": "hello"}}]}))
    registry = ToolRegistry()
    registry.register(
        PythonCallableTool(
            name="echo",
            description="Echo text",
            func=lambda args, state: args["text"].upper(),
        )
    )
    agent = AutomationAgent(provider=provider, registry=registry)
    results = agent.execute_workflow(agent.plan_workflow("use echo"))
    assert results[0].status == "success"
    assert results[0].output == "HELLO"


def test_prompt_blocked_by_safety():
    provider = DummyProvider(response=json.dumps({"steps": []}))
    registry = register_builtin_tools()
    safety = SafetyChecker(blocked_terms=["forbidden"])
    agent = AutomationAgent(provider=provider, registry=registry, safety=safety)
    with pytest.raises(SafetyViolationError):
        agent.plan_workflow("This prompt includes a forbidden phrase")


def test_plan_blocked_by_safety():
    provider = DummyProvider(
        response=json.dumps(
            {
                "steps": [
                    {
                        "tool": "analysis",
                        "description": "Plan to drop production database",
                    }
                ]
            }
        )
    )
    registry = register_builtin_tools()
    safety = SafetyChecker(blocked_terms=["drop production database"])
    agent = AutomationAgent(provider=provider, registry=registry, safety=safety)
    with pytest.raises(SafetyViolationError):
        agent.plan_workflow("Plan something risky")
