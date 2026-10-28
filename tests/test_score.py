from decimal import Decimal

from jd_parse.sample import held_out_ids, rule_fields
from jd_parse.schema import JobFields
from jd_parse.score import score_run, table


def fields(**kw):
    return JobFields(**kw).model_dump(mode="json")


USD = {"min": 100000, "max": 120000, "currency": "USD", "period": "year"}


def test_scores_each_field():
    labels = {
        1: fields(workplace="remote", open_to="anywhere", skills=["Python", "SQL"], pay=USD),
        2: fields(workplace="remote", open_to="unstated", skills=["Go"]),
    }
    predictions = {
        1: {
            "fields": fields(
                workplace="remote", open_to="anywhere", skills=["Python"], pay=dict(USD, max=120300)
            )
        },
        2: {"fields": fields(workplace="remote", open_to="anywhere", skills=["Go", "Rust"])},
    }
    s = score_run(labels, predictions)
    assert str(s.open_to) == "50% (1/2)"
    assert (s.anywhere.precision(), s.anywhere.recall()) == ("50%", "100%")
    assert (s.skills.tp, s.skills.fp, s.skills.fn) == (2, 1, 1)
    assert str(s.pay_exact) == "100% (1/1)"  # within half a percent


def test_a_failed_answer_counts_as_empty():
    labels = {1: fields(workplace="onsite", skills=["SQL"])}
    s = score_run(labels, {1: {"fields": None, "error": "invalid"}})
    assert s.failures == 1 and str(s.workplace) == "0% (0/1)" and s.skills.fn == 1


def test_table_has_a_column_per_run():
    s = score_run({1: fields()}, {1: {"fields": fields()}})
    out = table({"rules": s, "v1": s})
    assert out.splitlines()[0] == "| | rules | v1 |"


def test_rule_fields_translate_unlisted_columns():
    row = {
        "remote": True,
        "open_to": None,
        "comp_min": Decimal("90000.00"),
        "comp_max": None,
        "comp_currency": "USD",
        "comp_period": "year",
        "exp_min_years": 3,
        "exp_max_years": 5,
        "title": "Python Developer",
    }
    f = rule_fields(row, "Uses PostgreSQL")
    assert f.workplace == "remote" and f.open_to == "unstated"
    assert f.pay.min == 90000 and f.skills == ["PostgreSQL", "Python"]

    onsite = rule_fields(dict(row, remote=False, open_to="country"), "")
    assert onsite.workplace is None and onsite.open_to is None


def test_test_split_takes_the_same_share_of_every_group():
    rows = [{"id": i, "bucket": "anywhere"} for i in range(40)]
    rows += [{"id": 100 + i, "bucket": "region"} for i in range(20)]
    held = held_out_ids(rows, 0.3, "seed")
    assert sum(i < 100 for i in held) == 12 and sum(i >= 100 for i in held) == 6
    assert held == held_out_ids(rows, 0.3, "seed")
