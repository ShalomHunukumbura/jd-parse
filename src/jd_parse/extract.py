"""Runs one prompt with one model over the postings and saves every answer.

A run is a folder, data/runs/<prompt>__<provider>__<model>/, holding:

- predictions.jsonl  one row per posting: the fields (or the error), tokens and seconds
- meta.json          the prompt's hash, so an edited prompt can't mix into an old run

Postings already in predictions.jsonl are skipped, so a run interrupted by a rate limit
or a closed laptop carries on where it stopped.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from .providers import Provider, inline_refs
from .schema import JobFields, llm_json_schema
from .skills import SKILLS

# Long postings are mostly benefits and legal text. Cutting them keeps a 3B model's
# context (and a free tier's token budget) in reach. About 5,000 tokens.
MAX_CHARS = 20_000


def load_prompt(path: Path) -> str:
    skills = "\n".join(f"- {s.name} ({s.category})" for s in SKILLS)
    return path.read_text().replace("{skills}", skills)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


def run_dir(root: Path, prompt_path: Path, provider: Provider) -> Path:
    model = re.sub(r"[^A-Za-z0-9.-]+", "-", provider.model)
    return root / f"{prompt_path.stem}__{provider.name}__{model}"


def user_message(posting: dict) -> str:
    text = posting["text"]
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[... cut ...]"
    return (
        f"Title: {posting['title']}\n"
        f"Company: {posting['company']}\n"
        f"Location field: {posting['location'] or '(empty)'}\n\n"
        f"Description:\n{text}"
    )


def extract_one(provider: Provider, system: str, posting: dict, schema: dict) -> dict:
    """One posting. A reply that fails validation gets one chance to correct itself."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message(posting)},
    ]
    tokens_in = tokens_out = 0
    start = time.monotonic()
    fields = error = None
    for attempt in (1, 2):  # noqa: B007 (reported in the row)
        try:
            reply = provider.complete(messages, schema)
        except (httpx.HTTPError, RuntimeError) as exc:
            error = f"call failed: {exc}"
            break
        tokens_in += reply.input_tokens
        tokens_out += reply.output_tokens
        try:
            fields = JobFields.model_validate_json(reply.text).model_dump(mode="json")
            error = None
            break
        except ValidationError as exc:
            fields = None
            error = f"invalid: {exc.errors()[0]['msg']}"
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": f"That failed validation: {error}. Return fixed JSON."},
            ]
    return {
        "id": posting["id"],
        "fields": fields,
        "error": error,
        "attempts": attempt,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "seconds": round(time.monotonic() - start, 2),
    }


def run(
    provider: Provider, prompt_path: Path, postings: list[dict], runs_root: Path, limit: int | None
) -> Path:
    system = load_prompt(prompt_path)
    folder = run_dir(runs_root, prompt_path, provider)
    folder.mkdir(parents=True, exist_ok=True)

    meta_path = folder / "meta.json"
    meta = {"prompt": prompt_path.name, "prompt_hash": prompt_hash(system), "model": provider.model}
    if (
        meta_path.exists()
        and json.loads(meta_path.read_text())["prompt_hash"] != meta["prompt_hash"]
    ):
        raise SystemExit(
            f"{prompt_path.name} changed since {folder.name} was run. Save the new version as"
            " a new file (prompts/v2.md) so each score stays tied to the prompt that made it."
        )
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    predictions = folder / "predictions.jsonl"
    # A call that failed (rate limit, server error) says nothing about the model, so a
    # resumed run tries it again. The new row is appended; scoring keeps the last one.
    latest = {}
    if predictions.exists():
        latest = {row["id"]: row for row in map(json.loads, predictions.open())}
    done = {i for i, row in latest.items() if not (row["error"] or "").startswith("call failed")}
    todo = [p for p in postings if p["id"] not in done][:limit]
    print(f"{folder.name}: {len(done)} done, {len(todo)} to run")

    schema = inline_refs(llm_json_schema())
    with predictions.open("a") as out:
        for n, posting in enumerate(todo, 1):
            row = extract_one(provider, system, posting, schema)
            out.write(json.dumps(row) + "\n")
            out.flush()
            status = row["error"] or "ok"
            print(f"  [{n}/{len(todo)}] {posting['id']}  {row['seconds']:>6}s  {status}")
    return folder
