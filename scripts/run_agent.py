"""Command line interface for the automation agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from automation_agent import (
    AutomationAgent,
    EchoProvider,
    LLMProvider,
    OpenAIProvider,
    LlamaCppProvider,
    ProviderConfig,
    PythonCallableTool,
    ToolRegistry,
    register_builtin_tools,
)
from automation_agent.config import AutomationConfig, load_config


PROVIDER_FACTORY = {
    "echo": lambda cfg: EchoProvider(),
    "openai": lambda cfg: OpenAIProvider(
        model=cfg.model or "gpt-4o-mini",
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        **(cfg.options or {}),
    ),
    "llama": lambda cfg: LlamaCppProvider(
        model_path=cfg.options.get("model_path") if cfg.options else "model.gguf",
        **({k: v for k, v in (cfg.options or {}).items() if k != "model_path"}),
    ),
}


def build_provider(cfg: ProviderConfig) -> LLMProvider:
    factory = PROVIDER_FACTORY.get(cfg.name.lower())
    if not factory:
        raise ValueError(f"Unsupported provider '{cfg.name}'. Available providers: {', '.join(PROVIDER_FACTORY)}")
    return factory(cfg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PowerBI Advancer automation agent")
    parser.add_argument("prompt", help="Natural language description of the automation to create")
    parser.add_argument("--config", type=Path, default=Path("automation_config.yml"), help="Path to agent configuration")
    parser.add_argument("--context", type=Path, help="Optional JSON file with execution context")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: AutomationConfig = load_config(args.config)
    provider = build_provider(config.provider)
    registry: ToolRegistry = register_builtin_tools()

    if config.tools:
        for name, payload in config.tools.items():
            registry.register(
                PythonCallableTool(
                    name=name,
                    description=payload.get("description", name),
                    func=lambda args, state, body=payload.get("script", "return 'No-op'"):
                        exec_tool(body, args, state),
                )
            )

    agent = AutomationAgent(provider=provider, registry=registry, max_steps=config.max_steps)
    context: Dict[str, Any] = {}
    if args.context:
        context = json.loads(args.context.read_text(encoding="utf-8"))

    plan = agent.plan_workflow(args.prompt, context=context)
    results = agent.execute_workflow(plan, shared_state={})

    for result in results:
        print(f"[{result.status.upper()}] {result.step.tool}: {result.output}")


def exec_tool(body: str, args: Dict[str, Any], state: Dict[str, Any]) -> str:
    """Execute an inline Python tool body safely."""

    local_vars = {"args": args, "state": state}
    exec(body, {}, local_vars)
    output = local_vars.get("output")
    return str(output) if output is not None else ""


if __name__ == "__main__":
    main()
