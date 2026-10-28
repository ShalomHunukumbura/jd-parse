# jd-parse

Does an LLM read a job posting better than hand-written rules, and is it worth what it
costs? [Unlisted](https://findunlisted.link) already pulls remote scope, years of
experience, pay and skills out of ~20k postings with regular expressions. This project
labels a sample of postings by hand, runs free LLMs over the same postings, and scores
both against the labels, field by field.

The field that matters most is **where a remote job will hire from**. Most "Remote" jobs
are open to one country only; the ones truly open worldwide are a few percent, and
finding them is the point.

**Status:** in progress. The schema, labelling tool, model runner and scorer are built
and tested. Labels and the first results are next.

## Fields

| Field | Values |
|---|---|
| `workplace` | remote, hybrid, onsite |
| `open_to` | anywhere, region, country, unstated (remote jobs only) |
| `seniority` | intern, junior, mid, senior, lead, manager |
| `exp_min_years`, `exp_max_years` | years of experience required |
| `pay` | base pay min, max, currency, period |
| `skills` | from the same 85-skill dictionary as [hiring-warehouse](https://github.com/ShalomHunukumbura/hiring-warehouse) |

What each value means is in [LABELLING.md](LABELLING.md). The model's prompt follows the
same rules ([prompts/v1.md](prompts/v1.md)). The schema is enforced twice: the model is
given it as a JSON schema, and every reply is validated with Pydantic, which also checks
what a schema can't express (a pay max below the min, `open_to` on an on-site job). A
reply that fails gets one chance to correct itself.

## How it works

```
sample    Unlisted's Postgres -> data/postings.jsonl   (text + what the rules said)
label     you, in the terminal -> data/labels.jsonl    (pre-filled with the rules)
extract   prompt + model       -> data/runs/<prompt>__<provider>__<model>/
score     labels vs every run  -> a table, one column per run
```

- **The sample** is stratified by what Unlisted's rules said about remote scope, 20 per
  group, one posting per company. A plain random sample would hold two or three
  worldwide jobs.
- **Dev and test.** 30% of postings are held out. Prompts are tuned on `dev` only; `test`
  is scored once at the end, so the final number isn't flattered by tuning.
- **Runs are resumable and tied to their prompt.** An interrupted run carries on. Editing
  a prompt that already has results is refused: a changed prompt is a new file, so every
  score points at the exact text that produced it.

## Models

Everything runs free:

- `ollama:<model>`: a local model through [Ollama](https://ollama.com), e.g.
  `ollama:qwen2.5:3b`. No key, no limit, slow on a laptop CPU.
- `groq:<model>` and `gemini:<model>`: free tiers, through their OpenAI-compatible APIs.
  They are rate-limited; the runner waits and retries.

Token counts are recorded for every call, so the cost per 1,000 postings at paid prices
can be worked out without paying.

## Run it

```bash
uv sync
cp .env.example .env            # add UNLISTED_DATABASE_URL, and a free key if using one
uv run jd-parse sample          # draw ~100 postings
uv run jd-parse label           # label them (Enter keeps the pre-filled value)
uv run jd-parse extract ollama:qwen2.5:3b
uv run jd-parse score
uv run pytest
```

## Licence

MIT. Job descriptions belong to the companies that wrote them and are not included.
