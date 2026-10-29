# Results and change log

Every prompt change is scored on the 70 dev postings only. The 30 test postings are scored
once, at the end, with the prompt that came out best here.

## Label fixes made after seeing model output

Fixing labels only where a model disagrees makes the model look better, so every such fix
is listed here, and each one had to follow a rule already written in LABELLING.md.

| Posting | Split | Change | Rule |
|---|---|---|---|
| 1000047873, 1000050889, 1000051085, 1000059399, 1000059547 | dev | pay cleared | the pay came from Unlisted's ATS pay field; the text has none ("label the text") |
| 1000052490, 1000054978, 1000060573, 1000061497 | test | pay cleared | same, found by checking every label's pay against its text |
| 1000059931 | dev | open_to anywhere → region | location field "Remote - North America" is narrower than the text |
| 1000051085 | dev | workplace remote → empty | the text never says remote |

The pay fixes also lower the rules baseline: the rules read the ATS field, which the
models never see.

## v1 (prompts/v1.md)

| | rules | gpt-oss-120b |
|---|---|---|
| workplace | 80% | 90% |
| open_to, remote jobs | 48% | 80% |
| worldwide filter precision / recall | 14% / 100% | 80% / 100% |
| seniority | 0% | 47% |
| exp min / max | 66% / 84% | 94% / 96% |
| pay found precision / recall | 79% / 96% | 100% / 100% |
| pay exact, when stated | 89% | 86% |
| skills F1 | 93% | 94% |

Only a handful of dev postings are labelled worldwide, so the filter numbers move a lot
with one posting.

What the 120B misses had in common:

- **seniority, 25 of 37 misses:** null for titles with no level word, where the rule says
  "mid". Then "Senior Director" read as senior, and "Head of" / "Team Lead" as lead.
- **workplace, 4:** onsite guessed from a city in the location field.
- **open_to, 3:** a place in the location field of a remote job ignored ("Gilbert,
  Arizona", "North America - Remote").
- **pay, 4:** period left empty when the posting writes "$55—$60 USD" with no "per hour";
  currency left empty for "$" at a Canadian company.
- One-offs: "anywhere" with no evidence; monthly travel read as hybrid.

gpt-oss-20b failed 26 of 70 postings on its first run. 11 hit Groq's free limit of 200k
tokens a day, and 15 were Groq refusing the answer (`json_validate_failed`, empty output)
after the model spent a minute reasoning. The first are retried; the second now count as
the model's failures.

## v2 (prompts/v2.md)

Changes, one per v1 miss group: always give a seniority for a title, "mid" when there is
no level word; Director / Head of / VP are manager even when senior; a city alone isn't
onsite; monthly travel is still remote; the location field of a remote job counts as a
place; fill pay period and currency from the amount and the country.
