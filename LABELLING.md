# How to label

The score is only as good as the labels. Two people (or you on two days) should give the
same posting the same answer, so decide by these rules, not by feel. If a posting doesn't
fit them, label it your best way and write a note; notes are where rules get fixed.

Label what the posting **says**, not what you guess the company means.

## workplace

- `remote`: you can do the job without going to an office.
- `hybrid`: some days in an office are expected.
- `onsite`: the job is at a site.
- `-` (empty): the posting doesn't say.

Unlisted marks some jobs remote from the job board's own data, which the text may not
repeat. Label the text: if it never says, workplace is empty.

"Remote-first, with an office in Berlin you can use" is `remote`. "Remote, but you must
come in once a quarter" is still `remote`. "Two days a week in the office" is `hybrid`.

A city in the location field doesn't make a job `onsite`; the text has to say so.

## open_to (remote jobs only)

Where you can live and still be hired.

- `anywhere`: the posting says so: "worldwide", "work from anywhere", "any country", "we
  hire in 100+ countries". Plain "Remote" is **not** enough.
- `region`: more than one country but not all: EU, EMEA, Americas, LATAM, APAC, "Europe
  or Africa", "US or Canada".
- `country`: one country: "Remote - US", "must be based in the UK", "US citizens only".
- `unstated`: remote, and no place named anywhere in the posting.

Time zones: "must overlap 4 hours with US Eastern" is a working-hours rule, not a place
rule. If that's the only thing said, it's `unstated`. If it says "based in a US time zone",
that's `country`. A location field that is itself a time zone ("Remote - Europe Time
Zones", "Location: Central time zone") is a place rule: label the place.

The location field counts: a remote job listed as "Gilbert, Arizona" is `country`, one
listed as "North America - Remote" is `region`.

When the location field and the text disagree, the narrower one wins ("Remote" in the
location field, "must reside in Canada" in the text: `country`).

## seniority

From the title first, then the text.

- `intern`: intern, trainee, placement.
- `junior`: junior, associate, graduate, entry level, "I" in a ladder (Engineer I).
- `mid`: no level word and nothing in the text pointing up or down. Also "II".
- Director, Head of and VP are `manager` even with "Senior" in front. A title with two
  levels ("Senior/Staff") takes the lower one.
- `senior`: senior, "III".
- `lead`: staff, principal, lead, architect (an individual contributor above senior).
- `manager`: manages people: engineering manager, director, head of, VP.

A "Lead" who the text says manages a team is `manager`. The reverse holds too: a "Manager"
or "Director" title that is really an individual role (product manager, account manager,
field marketing manager, account director owning a book of business) is `mid`, or
`senior` when the title says senior, unless the text says they manage people.

## exp min / exp max

Years of experience asked for in the role, as numbers.

- "5+ years": min 5, max empty.
- "3-5 years": min 3, max 5.
- "at least 2 years of Python and 5 years overall": the overall figure, 5.
- Several different requirements and no overall one: the largest minimum.
- "Nice to have: 3 years of X": ignore preferred-only figures.
- Not stated: both empty, even if the title says Senior.

## pay

Base pay, as stated. Written as `min-max CUR period`, e.g. `120000-150000 USD year`.

- Leave out equity, bonus, commission and OTE.
- Several ranges by location: use the first one listed (usually the highest band) and
  write a note.
- Only one number ("up to $90k"): `-90000 USD year`. ("from $90k": `90000- USD year`.)
- Hourly and monthly stay as stated: `40-55 USD hour`.
- Period not written ("$55—$60 USD"): under 500 is `hour`, 500 to 20,000 is `month`,
  above is `year`.
- A bare `$` is USD, unless the job is in Canada (CAD), Australia (AUD) or another dollar
  country.
- No pay stated: `-`.

As with workplace, label the text only. Unlisted takes pay from Ashby's and Lever's
structured pay field when there is one, so the pre-filled pay can be a range the text never
mentions. If the text doesn't state it, pay is `-`.

## skills

Only skills in `src/jd_parse/skills.csv` count (85 of them). A skill counts when the
posting asks the candidate to know or use it, required or preferred. It doesn't count
when it's only in the company blurb ("we're the leading Python consulting firm") or a
list of what the *company's customers* use.

Watch the classic regex mistakes the pre-filled list will contain: "Go" in "go to
market", "R" as a letter, "Spark" as in "spark joy", a product called "Snowflake" in an
unrelated sense.

Editing: `+Kafka -Go` adds and removes; `=Python, SQL` replaces the whole list; `=` empties it.
