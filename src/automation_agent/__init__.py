"""LINA AUTOMATED agent package."""

from .agent import AutomationAgent, PlanStep, ActionResult
from .config import AutomationConfig, ProviderConfig, SafetyConfig, load_config
from .llm import LLMProvider, OpenAIProvider, LlamaCppProvider, EchoProvider
from .safety import (
    PromptSafetyEngine,
    PromptSafetyRule,
    RemoteGuardClient,
    RemoteGuardError,
    SafetyCoordinator,
    SafetyFinding,
    SafetyReport,
)
from .tooling import ToolRegistry, register_builtin_tools, BaseTool, PythonCallableTool, MCPTool

__all__ = [
    "AutomationAgent",
    "PlanStep",
    "ActionResult",
    "AutomationConfig",
    "ProviderConfig",
    "SafetyConfig",
    "load_config",
    "LLMProvider",
    "OpenAIProvider",
    "LlamaCppProvider",
    "EchoProvider",
    "PromptSafetyEngine",
    "PromptSafetyRule",
    "SafetyCoordinator",
    "RemoteGuardClient",
    "RemoteGuardError",
    "SafetyFinding",
    "SafetyReport",
    "ToolRegistry",
    "register_builtin_tools",
    "BaseTool",
    "PythonCallableTool",
    "MCPTool",
]
