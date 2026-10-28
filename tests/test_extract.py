import json

import pytest

from jd_parse import extract
from jd_parse.providers import Reply

POSTING = {
    "id": 1,
    "title": "Data Engineer",
    "company": "Acme",
    "location": "Remote",
    "text": "Remote worldwide. 5+ years of Python.",
    "split": "dev",
}
GOOD = json.dumps(
    {"workplace": "remote", "open_to": "anywhere", "exp_min_years": 5, "skills": ["Python"]}
)


class Fake:
    name = "fake"
    model = "m:1"

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    def complete(self, messages, schema):
        self.calls.append(messages)
        return Reply(self.texts.pop(0), 100, 20)


def test_valid_answer_is_kept_with_tokens():
    row = extract.extract_one(Fake(GOOD), "sys", POSTING, {})
    assert row["error"] is None and row["fields"]["open_to"] == "anywhere"
    assert (row["input_tokens"], row["output_tokens"], row["attempts"]) == (100, 20, 1)


def test_invalid_answer_gets_one_correction():
    bad = json.dumps({"workplace": "onsite", "open_to": "anywhere"})
    provider = Fake(bad, GOOD)
    row = extract.extract_one(provider, "sys", POSTING, {})
    assert row["error"] is None and row["attempts"] == 2 and row["input_tokens"] == 200
    assert "failed validation" in provider.calls[1][-1]["content"]


def test_two_invalid_answers_are_recorded_as_a_failure():
    row = extract.extract_one(Fake("not json", "still not"), "sys", POSTING, {})
    assert row["fields"] is None and row["error"].startswith("invalid")


def test_long_text_is_cut():
    long = dict(POSTING, text="x" * (extract.MAX_CHARS + 500))
    assert extract.user_message(long).endswith("[... cut ...]")


def test_run_resumes_and_refuses_an_edited_prompt(tmp_path):
    prompt = tmp_path / "v1.md"
    prompt.write_text("Extract.\n{skills}")
    second = dict(POSTING, id=2)

    folder = extract.run(Fake(GOOD), prompt, [POSTING], tmp_path / "runs", None)
    extract.run(Fake(GOOD), prompt, [POSTING, second], tmp_path / "runs", None)
    ids = [json.loads(line)["id"] for line in (folder / "predictions.jsonl").open()]
    assert ids == [1, 2]
    assert folder.name == "v1__fake__m-1"

    prompt.write_text("Extract better.\n{skills}")
    with pytest.raises(SystemExit, match="changed"):
        extract.run(Fake(GOOD), prompt, [POSTING], tmp_path / "runs", None)
