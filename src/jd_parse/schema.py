"""The fields we pull out of a job description.

The same model is used three ways: what a person labels, what the LLM must return, and what
the rule-based baseline is converted into. Scoring compares them field by field.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from .skills import SKILL_NAMES


class Workplace(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"


class OpenTo(StrEnum):
    """Where a remote job will hire from.

    `anywhere` needs the posting to say so ("worldwide", "any country"). A bare "Remote"
    with no place named is `unstated`: it often turns out to mean one country, which is
    exactly the confusion this project exists to measure.
    """

    anywhere = "anywhere"
    region = "region"
    country = "country"
    unstated = "unstated"


class Seniority(StrEnum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"  # staff, principal, lead: senior individual contributors
    manager = "manager"  # manages people: manager, director, head of


class PayPeriod(StrEnum):
    year = "year"
    month = "month"
    hour = "hour"


class Pay(BaseModel):
    """Base pay as stated in the posting. Equity, bonus and commission are left out."""

    min: float | None = Field(None, ge=0)
    max: float | None = Field(None, ge=0)
    currency: str | None = Field(None, description="ISO 4217 code, e.g. USD", max_length=3)
    period: PayPeriod | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Pay:
        if self.min is not None and self.max is not None and self.max < self.min:
            raise ValueError("pay max is below min")
        return self


class JobFields(BaseModel):
    workplace: Workplace | None = None
    open_to: OpenTo | None = Field(None, description="Only for remote jobs; null otherwise.")
    seniority: Seniority | None = None
    exp_min_years: int | None = Field(None, ge=0, le=40)
    exp_max_years: int | None = Field(None, ge=0, le=40)
    pay: Pay | None = None
    skills: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> JobFields:
        if self.open_to is not None and self.workplace != Workplace.remote:
            raise ValueError("open_to is only set for remote jobs")
        if (
            self.exp_min_years is not None
            and self.exp_max_years is not None
            and self.exp_max_years < self.exp_min_years
        ):
            raise ValueError("exp_max_years is below exp_min_years")
        unknown = sorted(set(self.skills) - SKILL_NAMES)
        if unknown:
            raise ValueError(f"skills not in the dictionary: {', '.join(unknown)}")
        # Order and repeats carry no meaning, so store a canonical form.
        self.skills = sorted(set(self.skills))
        return self


def llm_json_schema() -> dict:
    """The JSON schema sent to the model, with skills limited to the dictionary.

    Constrained decoding (Ollama, Gemini) then cannot produce a skill we don't know.
    """
    schema = JobFields.model_json_schema()
    schema["properties"]["skills"]["items"] = {"type": "string", "enum": sorted(SKILL_NAMES)}
    return schema
