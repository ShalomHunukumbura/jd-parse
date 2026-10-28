import json

import pytest

from jd_parse import label

RULES = {
    "workplace": "remote",
    "open_to": "anywhere",
    "seniority": None,
    "exp_min_years": 5,
    "exp_max_years": None,
    "pay": None,
    "skills": ["Go", "Python"],
}


def scripted(*answers):
    answers = iter(answers)
    return lambda prompt: next(answers)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("120000-150000 USD year", (120000, 150000, "USD", "year")),
        ("120k - 150k usd / year", (120000, 150000, "USD", "year")),
        ("-90000 USD year", (None, 90000, "USD", "year")),
        ("90000- GBP year", (90000, None, "GBP", "year")),
        ("40 to 55.5 EUR hour", (40, 55.5, "EUR", "hour")),
    ],
)
def test_parse_pay(answer, expected):
    pay = label.parse_pay(answer)
    assert (pay["min"], pay["max"], pay["currency"], pay["period"]) == expected


def test_parse_pay_clears_and_rejects():
    assert label.parse_pay("-") is None
    with pytest.raises(ValueError):
        label.parse_pay("lots")


def test_format_pay_round_trips():
    pay = label.parse_pay("120000-150000 USD year")
    assert label.parse_pay(label.format_pay(pay)) == pay


def test_edit_skills():
    assert label.edit_skills(["Go", "Python"], "+kafka -go") == ["Kafka", "Python"]
    assert label.edit_skills(["Go"], "=sql, python") == ["Python", "SQL"]
    assert label.edit_skills(["Go"], "=") == []
    with pytest.raises(ValueError):
        label.edit_skills([], "+Fortran 77")


def test_enter_keeps_every_rule_value():
    fields = label.ask_fields(RULES, scripted("", "", "", "", "", "", ""))
    assert fields == RULES


def test_corrections_and_a_bad_answer_retried():
    answers = scripted("r", "un", "sen", "", "8", "100k-120k usd year", "-go", "nonsense")
    fields = label.ask_fields(RULES, answers)
    assert fields["open_to"] == "unstated"
    assert fields["seniority"] == "senior"
    assert fields["exp_max_years"] == 8
    assert fields["pay"]["max"] == 120000
    assert fields["skills"] == ["Python"]


def test_non_remote_clears_open_to_without_asking():
    fields = label.ask_fields(RULES, scripted("hy", "", "", "", "", ""))
    assert fields["workplace"] == "hybrid" and fields["open_to"] is None


def test_run_saves_after_each_posting_and_resumes(tmp_path):
    path = tmp_path / "labels.jsonl"
    postings = [
        {
            "id": i,
            "split": "dev",
            "title": "T",
            "company": "C",
            "location": None,
            "text": "Remote worldwide",
            "rules": RULES,
        }
        for i in (1, 2)
    ]
    # Label the first, quit at the second.
    label.run(postings, path, ask=scripted("", "", "", "", "", "", "", "", "a note", "q"))
    saved = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["id"] for row in saved] == [1] and saved[0]["note"] == "a note"

    label.run(postings, path, ask=scripted("", "", "", "", "", "", "", "", ""))
    assert len(path.read_text().splitlines()) == 2


def test_review_shows_only_flagged_and_audit_drafts_and_measures_agreement(tmp_path):
    path = tmp_path / "labels.jsonl"
    postings = [
        {
            "id": i,
            "split": "dev",
            "title": "T",
            "company": "C",
            "location": None,
            "text": "Remote",
            "rules": RULES,
        }
        for i in (1, 2, 3)
    ]
    drafts = {
        1: {"id": 1, "fields": RULES, "note": "unsure", "by": "claude", "review": True},
        2: {"id": 2, "fields": RULES, "note": "", "by": "claude", "review": False, "audit": True},
        3: {"id": 3, "fields": RULES, "note": "", "by": "claude", "review": False},
    }
    label.save_labels(path, drafts)
    # Posting 1: change seniority. Posting 2 (audit): keep everything.
    label.run(
        postings,
        path,
        review=True,
        ask=scripted("", "", "", "sen", "", "", "", "", "", *[""] * 9),
    )
    saved = label.load_labels(path)
    assert saved[1]["changed"] and saved[1]["note"] == "unsure"
    assert not saved[2]["changed"] and saved[2]["by"] == "claude+human"
    assert saved[3]["by"] == "claude"
    assert label.agreement(saved).startswith("audit: 1 of 1")
