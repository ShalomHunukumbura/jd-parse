"""`jd-parse label`: hand-label postings in the terminal.

Each field starts filled in with what Unlisted's rules said, so most answers are Enter.
Labels are saved after every posting, so you can stop with `q` and carry on later.
Read LABELLING.md first: it says what each value means, and that's what makes 100 labels
consistent enough to score against.
"""

from __future__ import annotations

import json
import pydoc
import re
import shutil
import textwrap
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from .schema import JobFields, OpenTo, Pay, PayPeriod, Seniority, Workplace
from .skills import SKILL_NAMES

# Lines that usually decide a field. Shown first so you rarely need the whole text.
KEY_LINE = re.compile(
    r"remote|anywhere|worldwide|global|based in|located|location|time ?zones?|\bhours\b"
    r"|years|experience|salary|compensation|pay range|base pay|\$|€|£|usd|eur|gbp"
    r"|per (?:year|annum|hour|month)|hybrid|office|on-?site|relocat|visa|citizen",
    re.I,
)
SKILL_BY_LOWER = {name.lower(): name for name in SKILL_NAMES}
PAY_INPUT = re.compile(
    r"^\s*([\d.,]+k?)?\s*(?:-|to)?\s*([\d.,]+k?)?\s+([a-z]{3})\s*/?\s*(year|month|hour)\s*$",
    re.I,
)


class Quit(Exception):
    pass


def key_lines(text: str, limit: int = 25) -> list[str]:
    return [line for line in text.splitlines() if KEY_LINE.search(line)][:limit]


def format_pay(pay: dict | None) -> str:
    if not pay:
        return "-"
    low = "" if pay["min"] is None else f"{pay['min']:g}"
    high = "" if pay["max"] is None else f"{pay['max']:g}"
    return f"{low}-{high} {pay['currency'] or '???'} {pay['period'] or '?'}"


def _amount(value: str | None) -> float | None:
    if not value:
        return None
    value = value.replace(",", "").lower()
    return float(value[:-1]) * 1000 if value.endswith("k") else float(value)


def parse_pay(answer: str) -> dict | None:
    """'120k-150k USD year' -> a Pay dict. '-' clears it."""
    if answer.strip() == "-":
        return None
    match = PAY_INPUT.match(answer)
    if not match or not (match[1] or match[2]):
        raise ValueError("write pay as: 120000-150000 USD year  (or - for none)")
    return Pay(
        min=_amount(match[1]),
        max=_amount(match[2]),
        currency=match[3].upper(),
        period=PayPeriod(match[4].lower()),
    ).model_dump(mode="json")


def edit_skills(current: list[str], answer: str) -> list[str]:
    """'+Kafka -Go' adds and removes; '=Python, SQL' replaces the list; '=' empties it."""
    answer = answer.strip()
    if answer.startswith("="):
        names = [n.strip() for n in answer[1:].split(",") if n.strip()]
        return sorted({_skill(n) for n in names})
    skills = set(current)
    for op, name in re.findall(r"([+-])\s*([^+-]+)", answer):
        (skills.add if op == "+" else skills.discard)(_skill(name.strip()))
    return sorted(skills)


def _skill(name: str) -> str:
    try:
        return SKILL_BY_LOWER[name.lower()]
    except KeyError:
        raise ValueError(f"'{name}' is not in skills.csv") from None


def _choice(options: type, value: str | None, answer: str) -> str | None:
    if answer == "":
        return value
    if answer == "-":
        return None
    matches = [o.value for o in options if o.value.startswith(answer.lower())]
    if len(matches) != 1:
        raise ValueError(f"pick one of: {', '.join(o.value for o in options)}")
    return matches[0]


def _years(value: int | None, answer: str) -> int | None:
    if answer == "":
        return value
    return None if answer == "-" else int(answer)


def ask_fields(start: dict, ask: Callable[[str], str]) -> dict:
    """Walk the fields, each defaulting to `start`. Returns a validated label."""
    fields = dict(start)

    def field(prompt: str, apply: Callable[[str], object], key: str) -> None:
        while True:
            answer = ask(prompt).strip()
            if answer == "q":
                raise Quit
            try:
                fields[key] = apply(answer)
                return
            except ValueError as error:
                print(f"    {error}")

    field(
        f"  workplace [{fields['workplace'] or '-'}]: ",
        lambda a: _choice(Workplace, fields["workplace"], a),
        "workplace",
    )
    if fields["workplace"] == Workplace.remote:
        field(
            f"  open_to   [{fields['open_to'] or '-'}]: ",
            lambda a: _choice(OpenTo, fields["open_to"], a),
            "open_to",
        )
    else:
        fields["open_to"] = None
    field(
        f"  seniority [{fields['seniority'] or '-'}]: ",
        lambda a: _choice(Seniority, fields["seniority"], a),
        "seniority",
    )
    field(
        f"  exp min   [{_dash(fields['exp_min_years'])}]: ",
        lambda a: _years(fields["exp_min_years"], a),
        "exp_min_years",
    )
    field(
        f"  exp max   [{_dash(fields['exp_max_years'])}]: ",
        lambda a: _years(fields["exp_max_years"], a),
        "exp_max_years",
    )
    field(
        f"  pay       [{format_pay(fields['pay'])}]: ",
        lambda a: fields["pay"] if a == "" else parse_pay(a),
        "pay",
    )
    field(
        f"  skills    [{', '.join(fields['skills']) or '-'}]\n            +add -remove =replace: ",
        lambda a: edit_skills(fields["skills"], a),
        "skills",
    )
    return JobFields.model_validate(fields).model_dump(mode="json")


def _dash(value: object) -> str:
    return "-" if value is None else str(value)


def show(posting: dict, position: str) -> None:
    width = min(shutil.get_terminal_size().columns, 100)
    print("\n" + "=" * width)
    print(f"{position}  [{posting['split']}]  id {posting['id']}")
    print(f"{posting['title']}  -  {posting['company']}")
    print(f"location: {posting['location'] or '-'}")
    print("-" * width)
    for line in key_lines(posting["text"]):
        print(textwrap.shorten(line, width=width, placeholder=" ..."))
    print("-" * width)


def load_labels(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    with path.open() as f:
        return {row["id"]: row for row in map(json.loads, f) if row}


def save_labels(path: Path, labels: dict[int, dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for row in sorted(labels.values(), key=lambda r: r["id"]):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def run(postings: list[dict], labels_path: Path, relabel: bool = False, ask=input) -> None:
    labels = load_labels(labels_path)
    todo = [p for p in postings if relabel or p["id"] not in labels]
    print(f"{len(labels)} labelled, {len(todo)} to go. Enter keeps a value, - clears it.")
    print("At the first prompt: t = full text, s = skip, q = quit.")
    for n, posting in enumerate(todo, 1):
        show(posting, f"[{n}/{len(todo)}]")
        command = ask("  Enter to label, t/s/q: ").strip().lower()
        if command == "t":
            pydoc.pager(posting["text"])
        elif command == "s":
            continue
        elif command == "q":
            break
        start = labels.get(posting["id"], {}).get("fields") or posting["rules"]
        try:
            fields = ask_fields(start, ask)
        except Quit:
            break
        except ValidationError as error:
            print(f"  not saved: {error.errors()[0]['msg']}")
            continue
        note = ask("  note (optional): ").strip()
        labels[posting["id"]] = {"id": posting["id"], "fields": fields, "note": note}
        save_labels(labels_path, labels)
    print(f"{len(labels)} labelled. Saved to {labels_path}.")
