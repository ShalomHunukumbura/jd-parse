"""`jd-parse score`: compare runs with the hand labels, field by field.

A "run" is a folder under data/runs/, or `rules` for what Unlisted's hand-written rules
said. A posting a run failed on counts as an empty answer, so failures cost score instead
of quietly leaving the denominator.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .schema import JobFields

EMPTY = JobFields().model_dump(mode="json")


@dataclass
class Tally:
    right: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.right += ok
        self.total += 1

    def __str__(self) -> str:
        return f"{self.right / self.total:.0%} ({self.right}/{self.total})" if self.total else "-"


@dataclass
class PR:
    """Precision: of what it said, how much was right.

    Recall: of what's really there, how much it found.
    """

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, predicted: set, actual: set) -> None:
        self.tp += len(predicted & actual)
        self.fp += len(predicted - actual)
        self.fn += len(actual - predicted)

    def precision(self) -> str:
        return _pct(self.tp, self.tp + self.fp)

    def recall(self) -> str:
        return _pct(self.tp, self.tp + self.fn)

    def f1(self) -> str:
        denominator = 2 * self.tp + self.fp + self.fn
        return _pct(2 * self.tp, denominator)


def _pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if d else "-"


@dataclass
class Score:
    workplace: Tally = field(default_factory=Tally)
    is_remote: Tally = field(default_factory=Tally)
    open_to: Tally = field(default_factory=Tally)
    anywhere: PR = field(default_factory=PR)
    seniority: Tally = field(default_factory=Tally)
    exp_min: Tally = field(default_factory=Tally)
    exp_max: Tally = field(default_factory=Tally)
    pay_found: PR = field(default_factory=PR)
    pay_exact: Tally = field(default_factory=Tally)
    skills: PR = field(default_factory=PR)
    failures: int = 0
    tokens_in: list[int] = field(default_factory=list)
    tokens_out: list[int] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)


def same_pay(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return a is b

    def close(x, y):
        return (
            x is None
            and y is None
            or (x is not None and y is not None and abs(x - y) <= 0.005 * max(x, y))
        )

    return (
        close(a["min"], b["min"])
        and close(a["max"], b["max"])
        and a["currency"] == b["currency"]
        and a["period"] == b["period"]
    )


def score_run(labels: dict[int, dict], predictions: dict[int, dict]) -> Score:
    s = Score()
    for job_id, label in labels.items():
        row = predictions.get(job_id)
        if row is None:
            continue
        if row.get("error"):
            s.failures += 1
        got = row.get("fields") or EMPTY
        s.tokens_in.append(row.get("input_tokens", 0))
        s.tokens_out.append(row.get("output_tokens", 0))
        s.seconds.append(row.get("seconds", 0))

        s.workplace.add(got["workplace"] == label["workplace"])
        s.is_remote.add((got["workplace"] == "remote") == (label["workplace"] == "remote"))
        if label["workplace"] == "remote":
            s.open_to.add(got["open_to"] == label["open_to"])
        # The filter Unlisted needs: is this job really open worldwide?
        s.anywhere.add(
            {1} if got["open_to"] == "anywhere" else set(),
            {1} if label["open_to"] == "anywhere" else set(),
        )
        s.seniority.add(got["seniority"] == label["seniority"])
        s.exp_min.add(got["exp_min_years"] == label["exp_min_years"])
        s.exp_max.add(got["exp_max_years"] == label["exp_max_years"])
        s.pay_found.add({1} if got["pay"] else set(), {1} if label["pay"] else set())
        if label["pay"]:
            s.pay_exact.add(same_pay(got["pay"], label["pay"]))
        s.skills.add(set(got["skills"]), set(label["skills"]))
    return s


def rules_predictions(postings: list[dict]) -> dict[int, dict]:
    return {p["id"]: {"id": p["id"], "fields": p["rules"]} for p in postings}


def load_predictions(folder: Path) -> dict[int, dict]:
    with (folder / "predictions.jsonl").open() as f:
        return {row["id"]: row for row in map(json.loads, f)}


def table(scores: dict[str, Score]) -> str:
    rows = [
        ("workplace (remote/hybrid/onsite)", lambda s: str(s.workplace)),
        ("remote or not", lambda s: str(s.is_remote)),
        ("open_to, remote jobs", lambda s: str(s.open_to)),
        ("worldwide filter precision", lambda s: s.anywhere.precision()),
        ("worldwide filter recall", lambda s: s.anywhere.recall()),
        ("seniority", lambda s: str(s.seniority)),
        ("exp min years", lambda s: str(s.exp_min)),
        ("exp max years", lambda s: str(s.exp_max)),
        ("pay found: precision", lambda s: s.pay_found.precision()),
        ("pay found: recall", lambda s: s.pay_found.recall()),
        ("pay exact, when stated", lambda s: str(s.pay_exact)),
        ("skills precision", lambda s: s.skills.precision()),
        ("skills recall", lambda s: s.skills.recall()),
        ("skills F1", lambda s: s.skills.f1()),
        ("failed answers", lambda s: str(s.failures)),
        ("input tokens, mean", lambda s: _mean(s.tokens_in)),
        ("output tokens, mean", lambda s: _mean(s.tokens_out)),
        ("seconds per posting, median", lambda s: _median(s.seconds)),
    ]
    names = list(scores)
    lines = [
        "| | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for title, get in rows:
        lines.append(f"| {title} | " + " | ".join(get(scores[n]) for n in names) + " |")
    return "\n".join(lines)


def _mean(values: list[float]) -> str:
    return f"{statistics.mean(values):,.0f}" if values and any(values) else "-"


def _median(values: list[float]) -> str:
    return f"{statistics.median(values):.1f}" if values and any(values) else "-"
