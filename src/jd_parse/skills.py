"""The skill dictionary, and the regex matcher used as the skills baseline.

skills.csv is a copy of hiring-warehouse's seeds/skills.csv, so both projects count the
same skills. The matcher is the same idea as hiring-warehouse's skills.py, without its
speed-ups: we only run it over a few hundred postings.
"""

from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path

TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    pattern: re.Pattern[str]


DICTIONARY = Path(__file__).with_name("skills.csv")


def load_skills(path: Path = DICTIONARY) -> list[Skill]:
    with path.open(newline="") as f:
        return [
            Skill(
                row["skill"],
                row["category"],
                re.compile(row["pattern"], 0 if row["case_sensitive"] == "true" else re.I),
            )
            for row in csv.DictReader(f)
        ]


SKILLS = load_skills()
SKILL_NAMES = frozenset(skill.name for skill in SKILLS)


def find_skills(title: str, text: str) -> list[str]:
    """Every dictionary skill mentioned anywhere in the title or text."""
    full = f"{title}\n{text}"
    return sorted(skill.name for skill in SKILLS if skill.pattern.search(full))


def html_to_text(description_html: str | None) -> str:
    """Tags become line breaks, so "<li>Go</li><li>Python</li>" reads as two lines."""
    if not description_html:
        return ""
    text = html.unescape(TAG.sub("\n", description_html))
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
