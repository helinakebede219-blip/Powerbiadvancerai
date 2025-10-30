# LINA AUTOMATED

LINA AUTOMATED is a modular automation agent that turns natural language prompts into actionable workflows for analytics and data engineering teams. It provides:

- A planning agent that converts prompts into structured execution plans.
- Built-in tools for ingesting data, transforming datasets, publishing dashboards, and documenting assets.
- Extensible integrations with OpenAI-compatible providers (including Ollama), local Llama models, or custom Model Context Protocol (MCP) services.
- A CLI runner and configuration system for rapid experimentation and automation.
- A configurable prompt safety engine inspired by GPT-OS safeguards to detect risky requests before execution.

## Getting started

### Installation

```bash
pip install -e .
```

Optional extras are available for specific providers:

```bash
pip install -e .[openai]
pip install -e .[llama]
pip install -e .[mcp]
```

### Configure the agent

Edit `automation_config.yml` to select a provider, configure safety rules, and add custom tools. By default the project uses the deterministic `echo` provider so you can explore the workflow without external APIs.

```yaml
provider:
  name: openai
  model: gpt-4o-mini
  api_key: "$OPENAI_API_KEY"  # or set the environment variable
  base_url: "http://localhost:11434/v1"  # point at Ollama or other OpenAI-compatible endpoints
max_steps: 6
safety:
  enabled: true
  rules:
    - name: block_custom_keyword
      pattern: "ACME_TOP_SECRET"
      description: "Prevent leaking ACME secrets"
      severity: high
tools:
  build_dataset:
    description: Create a star schema dataset
    script: |
      output = f"Star schema created for {args['source']}"
```

### Run an automation

```bash
python scripts/run_agent.py "Create a daily refresh pipeline for the marketing dataset"
```

Sample output:

```
[SUCCESS] ingest_data: Ingested data from unknown source
[SUCCESS] transform_dataset: Applied transformation: cleaning and normalization
[SUCCESS] schedule_refresh: Scheduled refresh cadence: daily
```

### Using custom providers

- **OpenAI / GPT-OS safeguards** – set `provider.name` to `openai` and provide a valid API key. Use `base_url` to connect to OpenAI compatible guardrails or local gateways.
- **Ollama or other OpenAI-compatible runtimes** – reuse the `openai` provider and set `base_url` to the gateway URL.
- **Llama.cpp** – set `provider.name` to `llama` and supply `tools.options.model_path` to point at your GGUF model.
- **MCP bridges** – register `MCPTool` instances in Python or extend the configuration loader to spin up MCP clients for Creator tools.
- **Prompt safety** – toggle `safety.enabled` to disable checks or append custom regex rules for your organisation.

## Tests

```bash
pytest
```

## Interface mock

The repository ships with a lightweight landing page inspired by the Grok-style search interface. Open `web/lina_automated.html` in a browser to view the static mock for the "LINA AUTOMATED" UI shell.

## Next steps

- Connect the agent to your real MCP servers to orchestrate Creator tools.
- Extend the tool registry with Power BI REST API, Fabric, or Azure Automation operations.
- Deploy the CLI as part of your CI/CD process to provision analytics automation on demand.
