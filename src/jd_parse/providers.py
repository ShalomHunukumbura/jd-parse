"""One way to call every model we compare, all of them free.

- `ollama:<model>`  a local model through Ollama. No key, no limits, slow on a laptop CPU.
- `groq:<model>`    Groq's free tier, through its OpenAI-compatible API.
- `gemini:<model>`  Google's free tier, through its OpenAI-compatible API.

Each call returns the raw text plus the token counts, which is what cost is computed from
later. Rate limits on the free tiers are handled by waiting, never by giving up.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}
MAX_TRIES = 6


@dataclass
class Reply:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    name: str
    model: str

    def complete(self, messages: list[dict], schema: dict) -> Reply: ...


def inline_refs(schema: dict) -> dict:
    """Replace every {"$ref": "#/$defs/X"} with X itself.

    Pydantic writes nested models as references. Not every provider follows them, and a
    fully expanded schema means the same thing to all of them.
    """
    defs = schema.get("$defs", {})

    def expand(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return expand(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: expand(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    return expand(schema)


class Ollama:
    name = "ollama"

    def __init__(self, model: str, client: httpx.Client | None = None, num_ctx: int = 8192):
        self.model = model
        self.num_ctx = num_ctx
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.client = client or httpx.Client(base_url=host, timeout=600)

    def complete(self, messages: list[dict], schema: dict) -> Reply:
        response = self.client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                # Ollama turns the schema into a grammar, so the reply is always valid JSON
                # of this shape. It still has to be checked: the grammar can't express
                # rules such as "max is not below min".
                "format": schema,
                "stream": False,
                # The default context is small and Ollama silently drops what doesn't fit.
                "options": {"temperature": 0, "num_ctx": self.num_ctx},
            },
        )
        response.raise_for_status()
        body = response.json()
        return Reply(
            body["message"]["content"], body.get("prompt_eval_count", 0), body.get("eval_count", 0)
        )


class OpenAICompatible:
    def __init__(self, name: str, model: str, client: httpx.Client | None = None):
        base_url, key_var = OPENAI_COMPATIBLE[name]
        key = os.environ.get(key_var)
        if not key and client is None:
            raise SystemExit(f"set {key_var} (see .env.example)")
        self.name = name
        self.model = model
        self.client = client or httpx.Client(
            base_url=base_url, timeout=120, headers={"Authorization": f"Bearer {key}"}
        )
        # Not every model accepts a JSON schema. On the first refusal we fall back to
        # plain JSON mode with the schema written into the prompt, and stay there.
        self.schema_mode = True

    def complete(self, messages: list[dict], schema: dict) -> Reply:
        for attempt in range(MAX_TRIES):
            response = self.client.post("/chat/completions", json=self._body(messages, schema))
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(_wait_seconds(response, attempt))
                continue
            if (
                response.status_code == 400
                and self.schema_mode
                and "response_format" in (response.text)
            ):
                self.schema_mode = False
                continue
            response.raise_for_status()
            body = response.json()
            usage = body.get("usage") or {}
            return Reply(
                body["choices"][0]["message"]["content"] or "",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )
        raise RuntimeError(f"{self.name} still failing after {MAX_TRIES} tries: {response.text}")

    def _body(self, messages: list[dict], schema: dict) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": 0}
        if self.schema_mode:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "job_fields", "schema": schema},
            }
        else:
            body["response_format"] = {"type": "json_object"}
            system = messages[0]["content"] + "\n\nReturn JSON matching this schema:\n"
            body["messages"] = [
                {"role": "system", "content": system + json.dumps(schema)},
                *messages[1:],
            ]
        return body


def _wait_seconds(response: httpx.Response, attempt: int) -> float:
    try:
        return min(float(response.headers["retry-after"]), 120)
    except (KeyError, ValueError):
        return min(2 ** (attempt + 2), 120)


def make_provider(spec: str) -> Provider:
    """'ollama:qwen2.5:3b' -> Ollama('qwen2.5:3b'). Model names may contain colons."""
    name, _, model = spec.partition(":")
    if not model:
        raise SystemExit(f"write the model as provider:model, e.g. ollama:qwen2.5:3b (got {spec})")
    if name == "ollama":
        return Ollama(model)
    if name in OPENAI_COMPATIBLE:
        return OpenAICompatible(name, model)
    raise SystemExit(f"unknown provider '{name}': use ollama, groq or gemini")
