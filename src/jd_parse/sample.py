"""Draws the postings to label from Unlisted's database, with what Unlisted's rules said.

The sample is stratified by Unlisted's remote scope so the rare cases show up: only a few
percent of remote jobs say they are open worldwide, and a plain random 100 would hold two
or three of them. Each company appears once, so one big employer's template can't fill
the set. The draw is seeded, so the same database gives the same sample.

Every posting gets a split. `dev` is what prompts are tuned on. `test` is scored once at
the end; tuning on it would make the final number look better than it is.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .schema import JobFields, OpenTo, Pay, Workplace
from .skills import find_skills, html_to_text

BUCKETS = ("anywhere", "region", "country", "remote-unknown", "not-remote")

QUERY = """
WITH open_jobs AS (
    SELECT j.*, c.name AS company,
           CASE WHEN NOT j.remote THEN 'not-remote'
                ELSE coalesce(j.open_to, 'remote-unknown') END AS bucket,
           row_number() OVER (PARTITION BY j.company_id
                              ORDER BY md5(j.id::text || %(seed)s)) AS per_company
    FROM jobs j JOIN companies c ON c.id = j.company_id
    WHERE j.closed_at IS NULL AND length(j.description_html) > 200
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY bucket
                                 ORDER BY md5(id::text || %(seed)s)) AS per_bucket
    FROM open_jobs WHERE per_company = 1
)
SELECT id, title, company, location_raw, remote, open_to, comp_min, comp_max,
       comp_currency, comp_period, exp_min_years, exp_max_years, description_html, bucket
FROM ranked WHERE per_bucket <= %(per_bucket)s
ORDER BY bucket, id
"""


def rule_fields(row: dict, text: str) -> JobFields:
    """Unlisted's stored values, translated into our schema.

    The rules can't tell hybrid from on-site and don't guess seniority, so those stay
    empty. Their `open_to = NULL` on a remote job means "couldn't tell", our `unstated`.
    """
    pay = None
    if row["comp_min"] is not None or row["comp_max"] is not None:
        pay = Pay(
            min=row["comp_min"],
            max=row["comp_max"],
            currency=row["comp_currency"],
            period=row["comp_period"],
        )
    return JobFields(
        workplace=Workplace.remote if row["remote"] else None,
        open_to=(row["open_to"] or OpenTo.unstated) if row["remote"] else None,
        exp_min_years=row["exp_min_years"],
        exp_max_years=row["exp_max_years"],
        pay=pay,
        skills=find_skills(row["title"], text),
    )


def draw(url: str, per_bucket: int, test_share: float, seed: str) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.read_only = True
        rows = conn.execute(QUERY, {"seed": seed, "per_bucket": per_bucket}).fetchall()

    rng = random.Random(seed)
    postings = []
    for row in rows:
        text = html_to_text(row["description_html"])
        postings.append(
            {
                "id": row["id"],
                "split": "test" if rng.random() < test_share else "dev",
                "bucket": row["bucket"],
                "title": row["title"],
                "company": row["company"],
                "location": row["location_raw"],
                "text": text,
                "rules": rule_fields(row, text).model_dump(mode="json"),
            }
        )
    return postings


def write_postings(path: Path, postings: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for posting in postings:
            f.write(json.dumps(posting, ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]
