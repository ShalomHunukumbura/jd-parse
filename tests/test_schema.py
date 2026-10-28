import pytest
from pydantic import ValidationError

from jd_parse.schema import JobFields
from jd_parse.skills import find_skills, html_to_text


def test_skills_are_sorted_and_deduplicated():
    fields = JobFields(skills=["SQL", "Python", "SQL"])
    assert fields.skills == ["Python", "SQL"]


def test_unknown_skill_is_rejected():
    with pytest.raises(ValidationError, match="not in the dictionary"):
        JobFields(skills=["COBOL-ish"])


def test_open_to_needs_a_remote_job():
    with pytest.raises(ValidationError, match="only set for remote"):
        JobFields(workplace="hybrid", open_to="anywhere")


def test_experience_range_must_be_ordered():
    with pytest.raises(ValidationError):
        JobFields(exp_min_years=5, exp_max_years=3)


def test_pay_range_must_be_ordered():
    with pytest.raises(ValidationError):
        JobFields(pay={"min": 100, "max": 50, "currency": "USD", "period": "year"})


def test_html_to_text_keeps_list_items_apart():
    assert html_to_text("<ul><li>Go</li><li>Python&nbsp;3</li></ul>") == "Go\n\nPython 3"


def test_find_skills_reads_title_and_text():
    assert find_skills("Senior Python Engineer", "We use dbt and SQL.") == ["Python", "SQL", "dbt"]
