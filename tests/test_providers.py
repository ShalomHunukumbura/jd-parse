import json

import httpx
import pytest

from jd_parse import providers
from jd_parse.providers import Ollama, OpenAICompatible, inline_refs, make_provider
from jd_parse.schema import llm_json_schema

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "posting"}]
SCHEMA = {"type": "object"}


def client(handler, base="http://test"):
    return httpx.Client(base_url=base, transport=httpx.MockTransport(handler))


def chat_reply(text="{}", prompt=10, completion=3):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


def test_ollama_sends_schema_and_reads_token_counts():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": "{}"}, "prompt_eval_count": 7, "eval_count": 2}
        )

    reply = Ollama("qwen2.5:3b", client=client(handler)).complete(MESSAGES, SCHEMA)
    assert (reply.input_tokens, reply.output_tokens) == (7, 2)
    assert seen["format"] == SCHEMA and seen["options"]["temperature"] == 0


def test_rate_limit_waits_then_succeeds(monkeypatch):
    waits = []
    monkeypatch.setattr(providers.time, "sleep", waits.append)
    responses = iter([httpx.Response(429, headers={"retry-after": "3"}), chat_reply()])
    provider = OpenAICompatible("groq", "m", client=client(lambda r: next(responses)))
    assert provider.complete(MESSAGES, SCHEMA).input_tokens == 10
    assert waits == [3.0]


def test_falls_back_to_json_mode_when_schema_is_refused():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, text="response_format json_schema not supported")
        return chat_reply()

    provider = OpenAICompatible("groq", "m", client=client(handler))
    provider.complete(MESSAGES, SCHEMA)
    provider.complete(MESSAGES, SCHEMA)
    # One refusal, then plain JSON mode with the schema in the prompt, every time after.
    assert [b["response_format"]["type"] for b in bodies] == [
        "json_schema",
        "json_object",
        "json_object",
    ]
    assert '{"type": "object"}' in bodies[1]["messages"][0]["content"]


def test_make_provider_keeps_colons_in_model_names():
    assert make_provider("ollama:qwen2.5:3b").model == "qwen2.5:3b"
    with pytest.raises(SystemExit):
        make_provider("qwen")
    with pytest.raises(SystemExit):
        make_provider("openai:gpt")


def test_llm_schema_limits_skills_and_has_no_refs():
    schema = inline_refs(llm_json_schema())
    assert "Python" in schema["properties"]["skills"]["items"]["enum"]
    assert "$ref" not in str(schema) and "$defs" not in schema


def test_schema_validation_failure_comes_back_as_the_models_answer():
    def handler(request):
        error = {"code": "json_validate_failed", "failed_generation": ""}
        return httpx.Response(400, json={"error": error})

    reply = OpenAICompatible("groq", "m", client=client(handler)).complete(MESSAGES, SCHEMA)
    assert reply.text == ""


def test_other_errors_keep_the_response_body():
    def handler(request):
        return httpx.Response(401, text="invalid api key")

    with pytest.raises(RuntimeError, match="groq 401: invalid api key"):
        OpenAICompatible("groq", "m", client=client(handler)).complete(MESSAGES, SCHEMA)
