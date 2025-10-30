"""Core automation agent implementation."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .llm import LLMProvider
from .tooling import ToolRegistry, ToolExecutionError

LOGGER = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """Represents an actionable step the agent can execute."""

    tool: str
    description: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result returned by executing a plan step."""

    step: PlanStep
    status: str
    output: str


class AutomationAgent:
    """Agent that plans and executes automations based on prompts."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        *,
        max_steps: int = 10,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.max_steps = max_steps

    def plan_workflow(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> List[PlanStep]:
        """Create a structured workflow plan from a natural language prompt."""

        planning_prompt = self._build_planning_prompt(prompt, context=context)
        response = self.provider.generate(planning_prompt, context=context)
        steps = self._parse_plan_response(response)
        if not steps:
            LOGGER.info("Falling back to heuristic plan generation")
            steps = self._fallback_plan(prompt)
        return steps[: self.max_steps]

    def execute_workflow(
        self,
        steps: Iterable[PlanStep],
        *,
        shared_state: Optional[Dict[str, Any]] = None,
    ) -> List[ActionResult]:
        """Execute a workflow plan step-by-step using registered tools."""

        results: List[ActionResult] = []
        shared_state = shared_state or {}
        for step in steps:
            try:
                output = self.registry.execute(step.tool, step.args, shared_state)
                results.append(ActionResult(step=step, status="success", output=output))
            except ToolExecutionError as exc:
                LOGGER.exception("Tool execution failure for %s", step.tool)
                results.append(ActionResult(step=step, status="failed", output=str(exc)))
            except KeyError:
                message = f"No tool registered with name '{step.tool}'"
                LOGGER.warning(message)
                results.append(ActionResult(step=step, status="skipped", output=message))
        return results

    def _build_planning_prompt(
        self,
        user_prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Construct the system prompt that guides the LLM planning step."""

        tool_descriptions = "\n".join(
            f"- {tool.name}: {tool.description}" for tool in self.registry.tools.values()
        )
        context_blob = json.dumps(context, indent=2) if context else "{}"
        return (
            "You are PowerBI Advancer, an automation architect.\n"
            "Create a JSON object with a `steps` array. Each step must contain the fields\n"
            "`tool` (matching a registered tool name), `description`, and optional `args`.\n"
            "Only use the tools listed below. If a tool is missing, propose a descriptive\n"
            "step with `tool` set to `analysis`. Ensure JSON is valid.\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            f"Execution context: {context_blob}\n\n"
            f"User request: {user_prompt}\n"
        )

    def _parse_plan_response(self, response: str) -> List[PlanStep]:
        """Parse LLM output into structured plan steps."""

        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            payload = self._extract_json_blob(response)
        steps: List[PlanStep] = []
        if not payload:
            return steps
        for raw_step in payload.get("steps", []):
            if not isinstance(raw_step, dict):
                continue
            tool = str(raw_step.get("tool", "analysis"))
            description = str(raw_step.get("description", ""))
            args = raw_step.get("args") or {}
            if not isinstance(args, dict):
                continue
            steps.append(PlanStep(tool=tool, description=description, args=args))
        return steps

    def _fallback_plan(self, prompt: str) -> List[PlanStep]:
        """Heuristic plan builder when the LLM output cannot be parsed."""

        lowered = prompt.lower()
        heuristics = [
            ("power bi", "document_powerbi_report", "Review existing Power BI assets"),
            ("dataset", "transform_dataset", "Clean and transform the dataset"),
            ("schedule", "schedule_refresh", "Schedule refresh or automation triggers"),
            ("notify", "notify_team", "Communicate changes to stakeholders"),
            ("deploy", "publish_powerbi_dashboard", "Publish updated dashboard"),
        ]
        steps: List[PlanStep] = []
        for keyword, tool, description in heuristics:
            if keyword in lowered:
                steps.append(PlanStep(tool=tool, description=description))
        if not steps:
            steps.append(
                PlanStep(
                    tool="analysis",
                    description="Break down the user request into actionable subtasks",
                    args={"prompt": prompt},
                )
            )
        return steps

    def _extract_json_blob(self, text: str) -> Dict[str, Any]:
        """Extract JSON from a text block."""

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
