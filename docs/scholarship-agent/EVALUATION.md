# Extraction accuracy evaluation (2026-10-17)

Three separate measurements, never mixed:

| Set | What | Used for tuning? |
|---|---|---|
| Development fixtures (`tests/fixtures/scholarship`, `quality`) | 9 hand-made pages incl. German, French, Spanish, Indonesian, JSON-LD, PDF, conflicting dates | **Yes** - regression floor only (F1 1.00) |
| Held-out set A (`tests/heldout`, `heldout --set a`) | 30 real official pages and PDFs: 18 countries plus international organisations, 7 provider types, English/Spanish/Indonesian/German/Korean-site pages, 3 PDFs, deadline tables, age limits, closed and future cycles | Baseline was measured first and frozen; **afterwards** its errors drove fixes, so post-fix numbers on A are tuned |
| Held-out set B (`tests/heldout_b`, `heldout --set b`) | 13 real pages from 9 further sources, fetched and labelled **after** the fixes were frozen (commit `3c3b92c`..) | **No** - independent estimate |

Labels (`labels.json`) record for every page: URL, retrieval date, expected values, verbatim evidence spans and
an uncertainty note; "not_stated" marks facts the page does not establish, so any value extracted for them
counts as an unsupported claim. Page snapshots are kept locally (`tests/heldout*/pages`, gitignored, third-party
content) and can be re-downloaded with `heldout --fetch`.

## Results

Counts are correct/total. "Unsupported" = extracted values the page does not support / all scored extracted
values. "Missing" = labelled values left empty / all labelled values. "Attribution" = evidence snippets found
verbatim on the cited page.

| Run | deadline exact | deadline current vs past | nationality rule | funding amount + currency | age (min/max) | tuition | page kind | unsupported | missing | attribution |
|---|---|---|---|---|---|---|---|---|---|---|
| A baseline, rules | 5/20 | 5/5 | 6/11 | 3/10 | 14/18 | 2/5 | 20/30 | 5/19 | 25/46 | 130/161 |
| A baseline, rules + local 9B model | 10/20 | 10/10 | 7/11 | 7/10 | 15/18 | 2/5 | 20/30 | 8/32 | 15/46 | 159/190 |
| A after fixes (**tuned on A**) | 19/20 | 19/19 | 10/11 | 9/10 | 17/18 | 4/5 | 30/30 | 9/44 | 3/46 | 176/180 |
| **B independent, rules** | **3/5** | 3/3 | **3/8** | **2/3** | **3/6** | 1/3 | **9/13** | **5/15** | **6/21** | 63/79 → 71/71 * |
| B independent, rules + local 9B model | 3/5 | 3/3 | 3/8 | 3/3 | 5/6 | 1/3 | 9/13 | 7/20 | 4/21 | 75/91 |

\* the attribution fix (merged units now quote the page verbatim) was found while analysing set A; it changes
only evidence snippets, not extracted values, and was re-scored on B afterwards.

Model: `qwythos-hermes:latest` (9B) via local Ollama; 851 s for 30 pages, 329 s for 13 pages.

## Reading the numbers

- The gap between A-after-fixes and B is overfitting: rules written against A's failures do not transfer at the
  same rate. B is the honest estimate, and it is small (13 pages), so treat it as directional.
- Deadlines: tables, label/date line pairs, ranges ("from 28 March to 30 June 2022"), dates whose year is only
  stated once in the sentence are now read. Still missed on B: a deadline without any year on the page
  ("Tuesday 20 October"), two-digit years (`28/02/27`).
- Nationality: lists introduced by a heading and a following list ("Eligible countries" then one country per
  line) are the main remaining miss on B; the agent also picked up the host country from a sentence about the
  host. Explicit sentences ("citizens of X, Y and Z") are read reliably.
- Ages: maxima expressed per level ("Maximum age: Undergraduates ...: 35 years; Postdocs: 45") and "cannot be
  older than 35" were missed on B; a "minimum" was misread from "cannot be older than". The model fixes most
  age misses (5/6).
- Unsupported claims stay around one in three extracted values on B, mostly level words from navigation-like
  text and nationality picked from host-country sentences. Values are never marked verified because of this:
  verification re-reads the official page, and model readings are never promoted to confirmed.
- The AI pass lowers missing values but does not lower unsupported values; it is worth enabling for coverage,
  with the quote check as the guard.

## Three modes on the same pages (round 4, 2026-10-17)

Set B, unchanged labels, no tuning on it. Rules-only numbers are identical to the table above after the round 4
changes (quote injection guard, open-day guard).

| Mode | deadline exact | nationality | amount + currency | age | unsupported | missing | attribution | runtime |
|---|---|---|---|---|---|---|---|---|
| Rules | 3/5 | 3/8 | 2/3 | 3/6 | 5/15 | 6/21 | 71/71 | ~1 s |
| Rules + local Ollama (`qwythos-hermes:latest`, 9B) | 3/5 | 3/8 | 3/3 | 5/6 | 7/20 | 4/21 | 83/83 | 356 s |
| Rules + Claude (`claude-opus-5-5`) | **not run** | | | | | | | |

Claude was not run because no Anthropic key was provided and paid calls were not authorised. The dry run
(`AI_PROVIDER=anthropic`, no `ANTHROPIC_ALLOW_PAID`) estimated the work instead: 8 of the 13 set-B pages reach the
model, about 24,600 input tokens, about **$0.23** at 800 output tokens per page and at most $0.74 if every
response used the 4,000-token cap. Set A: 24 of 30 pages, about 63,500 input tokens, about $0.64 (worst case
$2.17). Input tokens are estimated at ~3.5 characters per token, so actual counts will differ.

To run it: `ANTHROPIC_API_KEY=... AI_PROVIDER=anthropic ANTHROPIC_ALLOW_PAID=1 ANTHROPIC_MAX_REQUESTS_PER_RUN=10
ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=40000 ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=40000 ANTHROPIC_MAX_ESTIMATED_COST_USD=1
python3 -m scholarship_agent heldout --set b --ai` (the result includes `ai_usage` with real token counts).

## Round 5 (2026-10-17): after the evidence-reliability changes

Same sets and labels; nothing was tuned on set B. Every round 5 change was driven by the live-search pages
(Indian NSP, Sussex, Stanford, Campus France, gov.br) or by unit cases, then checked against A and B.

| Set, mode | deadline exact | nationality | amount | age | unsupported | missing | attribution | deadline P / R |
|---|---|---|---|---|---|---|---|---|
| A rules (tuned set) | 19/20 | 10/11 | 9/10 | 17/18 | 9/44 | 3/46 | 177/181 | 0.70 / 0.95 |
| **B rules (independent)** | 3/5 | 3/8 | 2/3 | 3/6 | 5/15 | 6/21 | 71/71 | 0.75 / 0.60 |
| B rules + Ollama 9B | 3/5 | 3/8 | 3/3 | 5/6 | 7/20 | 4/21 | 83/83 | 0.50 / 0.60 |
| B rules + Claude | not run (paid calls not authorised; dry-run estimate $0.23) | | | | | | | |

Set B is unchanged by round 5: the changes act mainly on verification (what may be confirmed), on dates
for institutions or events, and on quote windows, which these 13 pages barely exercise. One intermediate change
lost a set-B deadline (a too-broad prompt-injection filter matched "upload your documents"); it was narrowed
because it was wrong in general, not to recover the score. Precision/recall above are per extracted date;
"unsupported" is extracted values the page does not support. Held-out labels do not yet record deadline kind
(applicant vs institutional) or scope, so those are covered by unit tests, not by these scores.

## Round 6 (2026-10-18): cloud provider comparison

`python3 -m scholarship_agent compare --set b` scores every mode with the same code (`heldout.evaluate`), pages
and labels: exact-match rates, per-field precision / recall / F1, unsupported values, missing values, verbatim
evidence, and for AI modes the proposed / accepted / rejected-by-reason counts, quote alignment of the AI's own
evidence, latency, tokens and estimated cost. Labels in A and B do not cover scholarship name and provider, field
of study, GPA requirements, academic cycle, residency, or conflict handling, so those are not scored.

Status on 2026-10-18: **neither cloud evaluation has run.** No `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` is set
and paid execution is not enabled, so `compare` reports both as `not_run` with these dry-run estimates:

| Set | Pages reaching the model | Est. input tokens | Claude `claude-opus-5-5` typical / worst | Gemini `gemini-3.8-flash` typical / worst |
|---|---|---|---|---|
| B (13 pages) | 8 | ~24,600 | $0.23 / $0.74 | $0.04 / $0.14 |
| A (30 pages) | 24 | ~63,500 | $0.64 / $2.17 | $0.12 / $0.41 |

"Typical" assumes 800 output tokens per page, "worst" the full 4,000-token cap. Rules on B: unchanged from
round 5 (deadline 3/5, nationality 3/8, amount 2/3, age 3/6, unsupported 5/15, missing 6/21).

### Running it (smallest useful budget, set B)

```bash
python3 -m scholarship_agent compare --set b            # 1. free: shows the estimate, sends nothing
# 2. Claude (an API key from console.anthropic.com with credits; a Claude app or Claude Code login is not one)
export ANTHROPIC_API_KEY=...            # your shell only, never a file in the repo
ANTHROPIC_ALLOW_PAID=1 ANTHROPIC_MAX_REQUESTS_PER_RUN=10 ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=40000 \
ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=40000 ANTHROPIC_MAX_ESTIMATED_COST_USD=1 \
python3 -m scholarship_agent compare --set b --providers rules,anthropic
# 3. Gemini (a key from aistudio.google.com; a Google One / Gemini app subscription is not one)
export GEMINI_API_KEY=...
GEMINI_ALLOW_PAID=1 GEMINI_MAX_REQUESTS_PER_RUN=10 GEMINI_MAX_INPUT_TOKENS_PER_RUN=40000 \
GEMINI_MAX_OUTPUT_TOKENS_PER_RUN=40000 GEMINI_MAX_ESTIMATED_COST_USD=0.25 \
python3 -m scholarship_agent compare --set b --providers rules,gemini
python3 -m scholarship_agent ai-usage                   # 4. what was actually spent
```

A run stops before any request whose worst case would cross a budget and is then reported as `partial`.
Answers are cached per provider, model and page, so a re-run costs nothing unless pages or prompts change.

## Round 7 (2026-10-17): Claude only

Claude is the only active AI provider; Gemini and Ollama remain in the code but are not evaluated or developed.
`compare` now defaults to `--providers rules,anthropic`. The Claude prompt gained fields (provider, cycle, fields
of study, residency, funding duration, living allowance / accommodation / insurance / travel, page conflicts), so
the set-B estimate is now ~26,300 input tokens, **$0.23 typical / $0.75 worst case**, still inside the $1 cap of
the command above. **The Claude evaluation has still not run**: `ANTHROPIC_API_KEY` is not set. Rules on B are
unchanged (deadline 3/5, nationality 3/8, amount 2/3, age 3/6, unsupported 5/15, missing 6/21, quotes 71/71).

## Round 8 (2026-10-17): cost-cap audit before the Claude run

The documented $1 cap was checked against the implementation before any paid run. Four gaps were found and closed:

| Gap | Risk | Fix |
|---|---|---|
| The SDK retried timeouts, connection errors and 5xx on its own (`max_retries=3`), invisible to the budget | a timed-out request may still be billed, then retried | SDK retries off; the agent retries itself, re-checks the budget for every attempt, and books a timed-out attempt at its worst case |
| Input tokens were estimated at 3.5 characters per token | under-estimate on non-Latin pages, so the input and cost checks could be passed | Anthropic's token-counting endpoint is used before each paid request (count + 5%), the character estimate only if counting fails |
| Server-side fallback could answer with another model at another price | cost above the estimate | fallback is opt-in (`ANTHROPIC_SERVER_FALLBACK=1`); an unknown served model is charged at the dearest known price |
| Budgets are per run, so repeated runs add up | several $1 runs | optional `ANTHROPIC_MAX_TOTAL_COST_USD` caps the total across runs in one data directory |

Simulated worst case for the documented set-B command (mocked API: inputs counted at 2.5 characters per token,
every answer using the full 4,000-token output cap): 8 requests, 32,276 input and 32,000 output tokens,
**$0.77**, so the run completes under $1. Typical (800 output tokens per page): $0.26. These are simulations of
the budget logic, not API results.

**The Claude evaluation has still not run**: `ANTHROPIC_API_KEY` is not set.

### Simulated-answer audit of the validator (not an API evaluation)

Plausible right and wrong Claude answers were built from real sentences of development set A pages (not set B)
and passed through `ai_extract.validate`.

| Set of cases | Cases | Wrong verdicts before fixes | After fixes |
|---|---|---|---|
| Audit cases (used to make the fixes) | 20 | 7 | 0 |
| Fresh cases written after those fixes | 12 | 3 | 0 (these were then also used for fixes) |

Fixed: an open day accepted as an opening date; "2027-28" not matched to "2027/2028" while a decade "2024–2033"
was accepted as a cycle; a website accepted as the funder; "citizen or permanent resident" accepted as a residency
requirement; "18 years old" and an extension period accepted as funding durations, and "3 years" rejected as 36
months; travel listed under "Visa costs we will not reimburse" accepted as covered; "towards education costs
(tuition and fees)" accepted as full tuition. The fresh-set result (3 of 12 wrong) is the honest estimate of how
often such answers slipped through before these fixes; no independent estimate exists for after them.

## First real Claude evaluation (2026-10-17, set B, API)

`claude-opus-5-5`, effort `low`, through the official SDK, user-scoped key with `ANTHROPIC_WORKSPACE_ID`; documented
budget (10 requests, 40k input, 40k output, $1 per run, $1 total). Exact input tokens were counted (free endpoint)
before the run: 31,189, worst case $0.77. Raw result: `tests/heldout_b/results/compare_claude_2026-10-17.json`.

| Mode | deadline exact | nationality | amount | age | duration | tuition | unsupported | missing | quotes verbatim |
|---|---|---|---|---|---|---|---|---|---|
| Rules | 3/5 | 3/8 | 2/3 | 3/6 | 0/2 | 1/3 | 5/15 (33%) | 6/21 (29%) | 71/71 |
| **Rules + Claude** | 3/5 | **4/8** | **3/3** | **5/6** | **1/2** | 1/3 | **5/19 (26%)** | **3/21 (14%)** | **93/93** |

Precision / recall per extracted date, level and country are identical in both modes (deadlines 0.75 / 0.60):
Claude only fills fields the rules left empty. Usage: 8 requests, 31,189 input + 5,216 output tokens, **$0.229**
estimated at list price (the Console bill is authoritative), 58 s wall time, mean latency 6.7 s per page (max 8.2 s),
no errors, no retries.

Claude proposed 66 values; 11 were rejected by the quote validator and 22 were stored (the rest repeated values the
rules already had, or lost to a first answer for the same field); every stored quote is verbatim on its page.
Manual audit of the 11 rejections: 6 correct (e.g. "Sept 2027 - Sept 2029" is not the 2027/2028 cycle; a quote that
says only "eligible countries listed below"), 5 wrong (two-digit-year dates "01/10/26" and "28/02/27", which were
right; "two years" not read as 24 months; "an ICP Connect Scholarship by VLIRUOS" and "Foundation is opening a 2026
Call" not accepted as funder statements). Those are set-B findings: they are recorded, **not fixed**, so set B stays
an independent test. Model deadlines remain `expected_unconfirmed`; nothing Claude read was confirmed.

## Round 10 (2026-10-17): independent set C, validator and per-level fixes

**Set C** (`tests/heldout_c`): 20 real pages fetched 2026-10-17 (VLIR-UOS programme, call and country pages, OeAD
Ernst Mach pages, ITS relay, Mundus Journalism, AMINEF Fulbright, Türkiye Bursları, University of Twente). Pages
were split dev / test before labelling (per site group, by sha256 of the id). Labels and 117 candidate answers
("claims": field, value, verbatim quote, accept or reject, why) were written from the pages before any round 10
change (`tests/heldout_c/make_labels.py`; no extractor or model output used). Labels revision 2 only removed
duplicate max/min ages on per-level pages. Snapshots are gitignored (`heldout --set c --fetch`).

Validator on the claims (`heldout --set c --split dev|test`, `validator` section):

| Claims | Before round 10 | After fixes, frozen at `e040759` | After post-test fixes |
|---|---|---|---|
| C-dev (used for development) | 13/34 wrong rejections, 10/26 wrong acceptances | 0/34, 1/26 | 0/34, 1/26 |
| **C-test (independent at `e040759`)** | **15/38, 7/19** | **2/38 (5%), 2/19 (11%)** | 0/38, 1/19 (no longer independent) |

Post-test fixes, found on C-test and therefore excluded from the independent number: age statements without the word
"age" ("cannot be older than"), "1 academic year", deadline quotes that state only a start date.

Rules on set C after round 10 (test half): per-level ages 6/6 (before: 0/6, and the VLIR pages were read as a
*minimum* age of 35), funding components 11/12 (before 7/12), deadline exact 5/7, nationality 5/5, unsupported
2/22, missing 4/24, quotes verbatim 76/76.

Set B: the round 9 numbers above remain the historical independent result. Re-scored with round 10 code it is no
longer independent (its round 9 findings motivated the work): rules unsupported 4/14, missing 7/21; the cached
round 9 Claude answers replayed through the new validator (no API call): deadline 4/5, nationality 4/8, amount 3/3,
unsupported 4/17, missing 5/21, quotes 93/93. 4 of the 5 round 9 false rejections are now accepted; "Foundation is
opening a 2026 Call" is still rejected as not a funding statement.

Claude on set C: **not run** (paid runs need explicit authorisation). Dry-run estimate with `claude-opus-5-5`:
C-dev 9 pages ~30.8k input tokens, $0.27 typical / $0.84 worst; C-test 10 pages ~32.6k, $0.29 / $0.93. Character
estimates under-counted set B input by ~13%. The prompt changed (new `age_limits_by_level` field), so the set-B
cache does not apply. Command for the test half, $1 cap:

```bash
( . ~/.config/scholarship-agent/anthropic.env; export ANTHROPIC_API_KEY ANTHROPIC_WORKSPACE_ID
  ANTHROPIC_ALLOW_PAID=1 ANTHROPIC_MAX_REQUESTS_PER_RUN=12 ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=45000 \
  ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=48000 ANTHROPIC_MAX_ESTIMATED_COST_USD=1 ANTHROPIC_MAX_TOTAL_COST_USD=2 \
  python3 -m scholarship_agent compare --set c --split test )
```

### Claude on C-test (2026-10-17, API, validator frozen at `f32333f`)

`claude-opus-5-5`, effort `low`; budget 12 requests, 45k input, 48k output, $1 per run, $1.25 total. 10 requests,
40,255 input + 6,122 output tokens, **$0.283** (list-price estimate), wall time 69 s, latency mean 6.3 s, max 9.1 s,
no errors or retries. Raw: `tests/heldout_c/results/`.

| C-test (10 pages) | Rules | Rules + Claude |
|---|---|---|
| Deadline exact / status | 5/7, 5/5 | **7/7, 7/7** |
| Deadline precision / recall | 0.83 / 0.71 | 0.88 / **1.00** |
| Openings recall | 0.50 | **1.00** |
| Nationality | 5/5 | 5/5 |
| Ages per level | 6/6 | 6/6 |
| Funding components | 11/12 | 11/12 |
| Amount + currency | 0/2 | **2/2** |
| Duration | 1/2 | **2/2** |
| Unsupported values | 2/22 | 2/25 |
| Missing values | 4/24 | **0/24** |
| Quotes verbatim | 76/76 | 101/101 |

Both remaining unsupported values come from the rules (an opening date also read as a deadline; tuition paid from the
allowance). Claude's 93 proposals: 25 stored (all quotes verbatim), 10 rejected by the validator - 5 rightly (a
programme's length as funding duration, "Sept 2027 - Sept 2029" as a cycle, "full scholarships" as full tuition, a
website and a bare name as funders) and 5 values that were right but whose quote did not state them (a deadline quoted
as "28 February 2027" without its heading, two Türkiye funder lines, a fields-of-study heading, VLIRUOS via its
website). Accepted but wrong: "OeAD" as funder from "evidence of own funds to the OeAD agency" (the funder check
matched "funds"), and study levels, which are not quote-checked. Claude deadlines stay `expected_unconfirmed`.

## Round 11 (2026-10-17): funder identity and study levels (no paid calls)

Root causes: the funder check accepted any quote containing a funding word anywhere ("own **funds** to the OeAD
agency"), and study levels were not checked against their quote at all; the rules also attached every level named
anywhere on a page to one piece of evidence. Now `evidence.organisation_role` classifies the named organisation as
funder, provider, host, own funds, mentioned or absent from the quote itself, and only funder or provider passes;
`study_levels_supported` requires each level to be stated as offered (not as a prerequisite such as "holding a
doctoral degree", nor excluded as in "not for undergraduate or PhD study"). Rules keep one evidence item per level.

Developed on C-dev only: 18 new dev claims (labels revision 3; the test half is byte-identical, fingerprint
`b5104708d9025059`). C-dev: funder wrong acceptances 4/7 → 1/7 (the remaining one, AMINEF's line about a separate,
paused DIKTI programme, needs programme context the quote lacks), study levels 6/6 → 0/6, no new wrong rejections.

**Diagnostic re-scores (not independent; the historical results above stand):** C-test claims 0/38 wrong
rejections, 1/19 wrong acceptances (unchanged). Cached C-test Claude answers replayed through the new validator, no
API call: accuracy unchanged (deadlines 7/7, missing 0/24, unsupported 2/25); "OeAD" from "own funds" and the
unsupported levels "postdoc, short_course" are now rejected; 24 values stored instead of 25. Set B replay: the Ernst
Mach "phd, postdoc" levels not stated in their quote are now rejected; scores otherwise unchanged.

## Set D (round 12, 2026-10-17): independent, frozen at `e1b09de`

28 pages fetched 2026-10-17 from 20 providers on 24 sites (16 host countries/territories plus one international foundation), none shared with A, B or C
(domain, normalised URL and page-text checks in `tests/heldout_d/freeze.py`, results in `manifest.json`): Swiss
Government Excellence Scholarships (federal pages and a South African government relay), Australia Awards Indonesia
(English and Indonesian; one page is co-funded with LPDP, a set-A provider), Gates Cambridge, Mandela Rhodes, KAUST,
TaiwanICDF, MOE Taiwan (via TECO Tel Aviv), Brunei/UBD, Malaysia MIS, Studienstiftung and KAS (German, one PDF
from 2014), Vanier, Mastercard Foundation and McGill, Czech Government, UTokyo and MEXT (two PDFs, one unreadable),
Hong Kong PhD Fellowship (RGC and HKU), ARES (French), Beasiswa Unggulan (Indonesian PDF), AMEXCID (Spanish).
Labels and 105 candidate answers (59 accept, 46 reject) written from the pages before any Claude run; all pages
are test pages. Scoring now counts only applicant deadlines and adds funder identity, cycle and per-level amounts.

Independent results at `e1b09de` (no model): rules - deadline exact 9/12, deadline P/R 0.82/0.75, nationality 2/8,
levels P/R 0.68/0.79, cycle 6/11, funding components 13/21, funder identity 0/11 (rules do not extract it),
unsupported 13/47 (28%), missing 31/74 (42%), quotes verbatim 217/220. **Validator on the 105 answers: 11/59
correct answers wrongly rejected (19%), 18/46 wrong answers wrongly accepted (39%)** - far worse than C-test
(5% / 11%), so the round 10-11 fixes partly fitted the VLIR/OeAD templates of set C.

Claude on D: **run 2026-10-17** (authorised; `claude-opus-5-5`, code, validator and labels unchanged at `e1b09de`).
24 requests in two runs (the first stopped at the 100k input-token limit after 22 pages; the second sent the last 2),
109,887 input + 12,437 output tokens, **$0.688**, latency mean 5.2 s / max 7.5 s. Rules -> rules + Claude: deadline
exact 9/12 -> 10/12, cycle 6/11 -> 9/11, funder 0/11 -> 4/11, amount 1/5 -> 5/5, components 13/21 -> 14/21,
nationality 2/8 -> 3/8, age 1/4 -> 2/4, unsupported 28% -> 23%, missing 42% -> 24%, Claude quotes 43/43 verbatim.
Validator on Claude's 193 real answers (post-hoc audit): 2 wrong acceptances of 129, 30 wrong rejections of 64.
Results: `tests/heldout_d/results/claude_opus_at_e1b09de.json`. Pre-run estimate kept below for the record: Dry-run estimate with `claude-opus-5-5`: 24 pages, ~84k input
tokens (character estimate +15%), ~$0.65 typical, $2.25 worst case; the $1 cap stops the run before any request whose
worst case would cross it, so a long-answer run can end partial. Command:

```bash
( . ~/.config/scholarship-agent/anthropic.env; export ANTHROPIC_API_KEY ANTHROPIC_WORKSPACE_ID
  ANTHROPIC_ALLOW_PAID=1 ANTHROPIC_MAX_REQUESTS_PER_RUN=26 ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=100000 \
  ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=100000 ANTHROPIC_MAX_ESTIMATED_COST_USD=1 ANTHROPIC_MAX_TOTAL_COST_USD=1.55 \
  python3 -m scholarship_agent compare --set d --providers rules,anthropic > data/compare_d.json )
```

Re-run: `python3 -m scholarship_agent heldout --set d [--ai]`.

## Round 13 (2026-10-18): three-way validator, deadlines, multilingual evidence (diagnostic only)

Changes: `ai_extract.judge()` returns accepted / needs_review / rejected (`validate()` still returns a reason; a
`Review` reason means "a person decides"). Review values are not stored; they go to `opp.uncertainties`. Deadline
validation reads "on or before", "at the latest", "submission", application windows (end = deadline, start =
opening), the heading line above a bare date, and rejects dates under notification/result headings; a bare "by
<date>" goes to review. Deadlines keep an `applicant_group` or `programme` scope. Cycles accept "2027/8"; closed,
future and date-derived cycles go to review. French, Indonesian, Spanish and German deadline words, number words,
decimal commas, space/dot thousands, "1. 8. 2026" dates, benefit words, study levels and nationality adjectives.
Quote-claim checks: negated or third-party funders, the scholar paying, programme length vs funding period, band
minimums vs overall scores, amounts tied to one level, "only for" conditions, residence vs citizenship.

**All numbers below are diagnostic** (set D was seen before these changes; C-test re-scores are diagnostic since
round 11). No paid call: Claude answers are replayed from the cache.

| | before (frozen) | after round 13 |
|---|---|---|
| D labelled claims: false rejections | 11/59 | 0/59 (1 to review) |
| D labelled claims: false acceptances | 18/46 | 5/46 (16 to review) |
| D Claude replay: deadline exact | 10/12 | 12/12 |
| D Claude replay: missing / unsupported | 18/74, 14/62 | 12/74, 14/68 |
| D Claude replay: components | 14/21 | 17/21 |
| C-test claims FR / FA | 0/38, 1/19 | 0/38, 0/19 (2 to review) |
| C-dev claims FR / FA | 0/41, 1/37 | 0/41, 1/37 (2 to review) |

Set A rules and the fixtures are unchanged. Details: `tests/heldout_d/results/round13_diagnostic.json`. A fresh,
independent measure needs a new set E.

## Rounds 27-31 (2026-10-19): decision benchmarks

From round 27 the unit of measurement is the applicant's decision, scored by `tests/decisions.py`: for each labelled
programme, eligibility by nationality, funding class, application cycle and applicant deadline, each landing in
correct / wrong claim / sent to review / abstained. Every set (L, M, N, O; `tests/heldout_<x>/`) is official programme
pages fetched from hosts no earlier set used, labelled by hand with a quotation per decision and frozen (hash-checked
by `score_<x>.py`) before scoring. A set is scored once as a test set; afterwards it is development data.

| Fresh set | Decisions | Rules at the time: correct / wrong / review | Round-26 code on the same set |
|---|---|---|---|
| L (round 27) | 172 | 107 / 29 / 18 | 112 / 34 / 3 |
| M (round 28) | 160 | 102 / 28 / 16 | 103 / 37 / 2 |
| N (round 29) | 156 | 96 / 28 / 21 | 95 / 41 / 2 |
| O (round 30) | 120 | 70 / 17 / 17 | 71 / 26 / 4 |
| P (round 31) | 236 | 150 / 30 / 38 | 163 / 54 / 0 |

Since round 30 a rule change is kept only when `tests/devpool.py` (all used sets pooled; utility = correct - 2 x wrong -
0.5 x right answers held in review) rises without any set falling. Round 31 (dates stage 4, bracketed exclusion lists,
residence conditions, European demonyms, full cost of attendance) moved the pool from 364.5 to 388 (wrong claims 64 -> 56
on 660 decisions). Set P (59 programmes, 518 pages fetched from 518 new hosts in 54 countries, most of them university programme pages) was then scored once: round-31 code 150 correct / 30 wrong / 38 review; the round-30 code on the same pages 148 / 31 / 39; the round-26 code 163 / 54 / 0. Per decision (round 31): eligibility 41 / 4 / 9, funding 13 / 16 / 24, cycle 41 / 8 / 5, deadline 55 / 2 / 0. The funding class is the weak decision: most set-P programmes are cash awards or tuition-discount tiers labelled "not stated" or "partially funded", and the rules read them as stipends, waivers or full funding. Leaving out the close calls (65 decisions): 121 / 18 / 19 (round 26: 130 / 29 / 0). Round 31 also tried and rejected: sending deadlines with three or more dates to review, unblocking
"announcement" and "guidance" pages, and letting a negated exclusion win over a later include.

**Claude-assisted extraction on the decision benchmark** (`tests/decisions_ai.py`, mode targeted, Opus 5.5, effort low,
69 requests, $0.80, every answer quote-checked): N 116 -> 118 correct with 11 wrong claims either way; O 80 -> 83 correct
with 6 wrong claims either way (review 18 -> 21). The first pass added three wrong "stipend" claims from grant totals
("The maximum Dissertation Fieldwork Grant is $25,000"); `ai_extract.validate` now sends such amounts to review. Both
sets were development data by then, so the gain is diagnostic.

**Documents** (`tests/docs_bench.py`): the reviewer is the gate every draft passes. On a synthetic profile with three
programmes and 24 planted faults it caught 17 and raised 9 false alarms before round 31; after mapping each
accomplishment claim to the matching fact category and demoting selection-criteria words to notes, it catches 24/24 with
no false alarm, and the assembled CV contains no number, year or name that is not a confirmed fact. The drafts were used
to make those two fixes, so the figure is diagnostic.
