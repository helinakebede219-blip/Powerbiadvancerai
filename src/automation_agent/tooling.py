"""Tool registry and execution helpers."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails during execution."""


@dataclass
class BaseTool:
    """Base representation of an automation tool."""

    name: str
    description: str

    def execute(self, args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        raise NotImplementedError


@dataclass
class PythonCallableTool(BaseTool):
    """Tool backed by a Python callable."""

    func: Callable[[Dict[str, Any], Dict[str, Any]], str]

    def execute(self, args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        try:
            return self.func(args, shared_state)
        except Exception as exc:  # pragma: no cover - defensive
            raise ToolExecutionError(str(exc)) from exc


@dataclass
class MCPTool(BaseTool):
    """Tool that bridges to a Model Context Protocol server."""

    action: str
    client_factory: Callable[[], Any]

    def execute(self, args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        try:
            client = self.client_factory()
        except Exception as exc:  # pragma: no cover - requires MCP runtime
            raise ToolExecutionError(f"Failed to create MCP client: {exc}") from exc
        try:
            response = client.perform_action(self.action, args=args, state=shared_state)
        except Exception as exc:  # pragma: no cover - requires MCP runtime
            raise ToolExecutionError(f"MCP action '{self.action}' failed: {exc}") from exc
        return str(response)


class ToolRegistry:
    """Container for registered tools."""

    def __init__(self) -> None:
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self.tools[tool.name] = tool

    def execute(self, name: str, args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        tool = self.tools[name]
        return tool.execute(args, shared_state)

    def extend(self, tools: List[BaseTool]) -> None:
        for tool in tools:
            self.register(tool)


def register_builtin_tools(registry: Optional[ToolRegistry] = None) -> ToolRegistry:
    """Create a registry with opinionated built-in tools."""

    registry = registry or ToolRegistry()

    def _update_state(key: str, value: Any, shared_state: Dict[str, Any]) -> None:
        shared_state.setdefault("history", []).append({key: value, "timestamp": _dt.datetime.utcnow().isoformat()})

    def ingest_data(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        source = args.get("source", "unknown source")
        _update_state("ingest", source, shared_state)
        return f"Ingested data from {source}"

    def transform_dataset(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        transformation = args.get("transformation", "cleaning and normalization")
        _update_state("transform", transformation, shared_state)
        return f"Applied transformation: {transformation}"

    def publish_dashboard(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        workspace = args.get("workspace", "default workspace")
        _update_state("publish", workspace, shared_state)
        return f"Published Power BI artifact to {workspace}"

    def document_report(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        title = args.get("title", "Power BI Report")
        _update_state("document", title, shared_state)
        return f"Generated documentation for {title}"

    def schedule_refresh(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        cadence = args.get("cadence", "daily")
        _update_state("schedule", cadence, shared_state)
        return f"Scheduled refresh cadence: {cadence}"

    def notify_team(args: Dict[str, Any], shared_state: Dict[str, Any]) -> str:
        channel = args.get("channel", "email")
        _update_state("notify", channel, shared_state)
        return f"Sent notification via {channel}"

    registry.extend(
        [
            PythonCallableTool(
                name="ingest_data",
                description="Load raw datasets from cloud or local sources",
                func=ingest_data,
            ),
            PythonCallableTool(
                name="transform_dataset",
                description="Transform and enrich tabular datasets",
                func=transform_dataset,
            ),
            PythonCallableTool(
                name="publish_powerbi_dashboard",
                description="Publish dashboards or semantic models to a workspace",
                func=publish_dashboard,
            ),
            PythonCallableTool(
                name="document_powerbi_report",
                description="Create documentation for Power BI reports",
                func=document_report,
            ),
            PythonCallableTool(
                name="schedule_refresh",
                description="Configure refresh schedules or automation triggers",
                func=schedule_refresh,
            ),
            PythonCallableTool(
                name="notify_team",
                description="Send updates to collaborators",
                func=notify_team,
            ),
        ]
    )

    return registry


__all__ = [
    "BaseTool",
    "PythonCallableTool",
    "MCPTool",
    "ToolRegistry",
    "register_builtin_tools",
    "ToolExecutionError",
]
