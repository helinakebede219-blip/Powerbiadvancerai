"""Language model provider interfaces."""

from __future__ import annotations

import abc
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class LLMProvider(abc.ABC):
    """Abstract base class for providers."""

    @abc.abstractmethod
    def generate(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        """Return a text response from the model."""


class EchoProvider(LLMProvider):
    """Provider that returns a deterministic JSON echo."""

    def generate(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        return json.dumps({
            "steps": [
                {
                    "tool": "analysis",
                    "description": "Manual review required because no LLM provider was configured.",
                    "args": {"prompt": prompt},
                }
            ]
        })


class OpenAIProvider(LLMProvider):
    """Wrapper around the OpenAI Responses API."""

    def __init__(self, model: str = "gpt-4o-mini", *, api_key: Optional[str] = None, base_url: Optional[str] = None, **options: Any) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openai package is required for OpenAIProvider") from exc
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAIProvider requires an API key via parameter or OPENAI_API_KEY env var")
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.options = options

    def generate(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            **self.options,
        )
        return response.output[0].content[0].text


class LlamaCppProvider(LLMProvider):
    """Wrapper for llama.cpp models."""

    def __init__(self, model_path: str, *, temperature: float = 0.1, max_tokens: int = 1024, **options: Any) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("llama-cpp-python is required for LlamaCppProvider") from exc
        self.client = Llama(model_path=model_path, **options)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        response = self.client(
            prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response["choices"][0]["text"]


class OpenAICompatibleProvider(LLMProvider):
    """Provider that targets OpenAI-compatible REST APIs such as Ollama."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        request_timeout: float = 30.0,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.request_timeout = request_timeout
        self.options = options or {}

    def generate(self, prompt: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        payload_options = {k: v for k, v in self.options.items() if k != "system_prompt"}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(prompt, context=context),
        }
        payload.update(payload_options)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:  # pragma: no cover - depends on runtime
            raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc
        data = json.loads(body)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # pragma: no cover - service contract
            raise RuntimeError(f"Unexpected response structure: {data}") from exc

    def _build_messages(
        self, prompt: str, *, context: Optional[Dict[str, Any]] = None
    ) -> list[Dict[str, Any]]:
        messages: list[Dict[str, Any]] = []
        system_prompt = self.options.get("system_prompt")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        user_content = prompt
        if context:
            user_content = f"{prompt}\n\nContext:\n{json.dumps(context, indent=2)}"
        messages.append({"role": "user", "content": user_content})
        return messages


__all__ = [
    "LLMProvider",
    "EchoProvider",
    "OpenAIProvider",
    "LlamaCppProvider",
    "OpenAICompatibleProvider",
]
