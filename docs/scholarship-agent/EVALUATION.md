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
| Q (round 33, non-university funders) | 216 | 129 / 36 / 17 | 126 / 53 / 0 |

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

### Round 32 (set P as development data; writing standard)

With P in the pool (K to P, 896 decisions) the baseline was 473 (662 correct, 86 wrong, 103 review). Five funding-class
changes were kept, all judged on the pool: "up to 21 meals" is not a partial-tuition cap; "Full tuition fees / Partial
tuition fees" is a mixed extent; a scholarship page that also mentions assistantships is not an assistantship; a stated
partial extent beats a bare "waiver" note; "the minimum award amount is $2,500 per year" is not a stipend. Pool 473 ->
492.5 (668 correct, 79 wrong); set P alone 150 / 30 / 38 -> 155 / 24 / 38. Rejected: a covering-verb condition on "cost
of attendance" (cost two right answers on O and P), an application-fee-waiver guard, a general "yearly cash award is not
a stipend" rule (-3 correct on earlier sets), and a "monthly payment plan" guard (no effect).

**Claude on set P** (`tests/decisions_ai.py`, targeted, Opus 5.5, effort low, cap $0.70): 52 of 59 pages were
enriched for $0.66 (7 pages skipped by the cap), 175 values proposed, 58 accepted after quote checks. On the frozen
round-31 rules: 148 / 33 / 40 against 150 / 30 / 38 for the rules alone, the new wrong claims all "stipend" readings of
yearly cash awards. `ai_extract.validate` now sends any stipend amount whose quote lacks stipend/allowance/living/monthly
wording to review; rescored from the cache (no new spend) on the round-32 rules: P 157 / 26 / 39 against 155 / 24 / 38
(the two extra wrong claims are a monthly-paid award the label calls a close call, and a cash award), O 84 / 5 / 20
against 81 / 5 / 18, N 118 / 11 / 20 against 116 / 11 / 20. The model adds dates and cycle states the rules abstain on;
it does not help the funding class.

**Writing standard** (`documents.STANDARD`, `documents.standard()`): every brief now carries the structure of a strong
document of its kind (statement of purpose, motivation letter, personal statement, essay, research proposal, study plan,
career goals, leadership essay, academic CV) and the shared do/avoid lists committees and university writing centres
teach: a concrete opening instead of a quotation or "ever since I was a child", one idea per paragraph, specifics over
adjectives, every criterion answered with an example, named fit with the programme, a concrete plan at the end. The
skeleton lays the structure out as [YOU WRITE] slots; `review.py` flags filler phrases, a quotation opener and one-block
prose as warnings (never errors: the applicant decides). `tests/docs_bench.py` plants 30 faults, 30 caught, 0 false
alarms. The standard supplies no content; every sentence still rests on the fact pack.

### Round 33 (pool K to P; set Q)

Baseline with set P adjudicated (Miami OH: the label missed "you must hold citizenship in a country outside the United
States", `tests/heldout_p/adjudication.json`) and the round-32 rules: 523.5 is the figure after the round; the round
started from 492.5. Kept, each on the pool: a sentence about *other* scholarships states no nationality rule for this one;
a definition of "international student" or a procedural sentence ("U.S. citizens who studied abroad should follow the
international admissions requirements") is not a nationality rule; an approximate date ("typically in early October") is
no longer reported as a cycle state ("expected" removed: it was wrong four times in six); "rolling" is a cycle only when
the sentence is about applications, not about awards being made on a rolling basis; a question ("How long do holders
receive financial support?") or a budget instruction ("include a table showing ... graduate stipends") is not a funding
benefit. Rejected: treating a page whose only dates are over 15 months old as "not stated" rather than closed (lost three
right answers), moving "financial support" from stipend to award (lost nine), "may be offered" as undocumented (no gain),
and the definition guard on its own (no effect without the procedural clause). Pool 492.5 -> 523.5 (677 correct, 68
wrong, 102 review on 896 decisions); set P 155 / 24 -> 162 / 16 with the adjudication.

**Set Q** (`tests/heldout_q/`, 54 programmes from 178 pages, fetched 2026-10-20 from 178 hosts no earlier set used): the first
set with no university pages. The funders are governments and their agencies, binational commissions (Fulbright
commissions in 14 countries), foundations, companies and research councils, in 29 countries and 9 languages. 421 candidate
programmes were searched; 243 were not fetched (overlap with an earlier set's host, robots.txt refusing automated clients,
or no result on the official domain), and 124 fetched pages were excluded with the reason recorded (lists, home pages,
news, PDFs and pages not reviewed). Scored once: round-33 code 129 correct / 36 wrong / 17 review on 216 decisions; the
round-32 code gives the same 129 / 36 / 17 (the round-33 rules changed nothing on Q); round 30 128 / 38 / 18; round 26
126 / 53 / 0. Leaving out the close calls (164 decisions): 104 / 24 / 11 (round 26: 98 / 39 / 0). Clean quotations on
every claimed answer: 66/66. Per decision (round 33): eligibility 31 / 8 / 6, funding 25 / 10 / 9, cycle 35 / 8 / 2,
deadline 38 / 10 / 0.

What Q shows that P did not: **deadlines** are the weak decision on funder pages (10 wrong claims), because these pages
carry timelines (opening, closing, interviews, feedback, start dates, the previous cycle's dates) and the rules pick the
wrong one or an old one; on university pages (P) this decision was 55 / 2. **Eligibility**: "must not be a dual citizen
of the U.S." is read as including the US (five Fulbright pages), and "international students and Japanese students" as
"any". **Funding**: cash awards without a stated use are still read as stipends (five cases), and "fees" or
"assistantship" words on Fulbright benefit lists pull the class the wrong way. Q is now development data; the next
fresh set is R.


### Round 34 (pool K to Q, 1,112 decisions)

Set Q became development data and its errors drove the round, so its new scores are diagnostic, not a test. Kept, each on
the pool: "Open: ... / Close: ..." lines (the close is the deadline, not a second opening); "opening call" and "closing
call"; "deadline for sending feedback" is not an application deadline; "Application: <date> to <date>" is a window;
Spanish "desde el X hasta el Y" windows; "as of <date>" and degree or enrolment dates are conditions; "persons holding
dual Japan-U.S. citizenship are NOT eligible" names no second country; the country where the study takes place ("to study
... in the United States", "en los Estados Unidos") and "U.S. law" are not nationalities; "Canadian, permanent resident, and
international graduate students" is open to all. Rejected: a Spanish question guard (no effect), a guard for the menu
entry "Grants for United States Citizens" (no net gain), and a Spanish "desde" condition (no effect). Pool 579 -> 610
(815 correct, 93 wrong); set Q 129 / 36 / 17 -> 137 / 26 / 18 (deadline 38 / 10 -> 42 / 6, eligibility 31 / 8 -> 34 / 3).
Remaining deadline errors on Q are old-news dates, dates without a year, and a start-of-period date; the next fresh set is R.

**Claude on set Q** (targeted, Opus 5.5, effort low, cap $0.70): 50 of 54 pages enriched for $0.65 (4 skipped by the cap), 184 values
proposed, 54 accepted after quote checks. On the round-34 rules: 141 / 27 / 20 against 137 / 26 / 18 for the rules alone
(+4 correct, +1 wrong claim). The model fills dates and cycle states the rules abstain on (CHED, Fulbright Malaysia: closed
with the right deadline) and one stipend; it also asserted a deadline and a closed state for a page whose label is
"not stated" (Dutch-Bangla Bank). Total spent on Claude evaluations so far: $2.11.

### Round 35 (pool K to Q): funding sentences

Four more funding-sentence rules, each judged on the pool: "provides financial support for students" is a mission statement,
not a stipend; "processes scholarship payments" is administration; "University and College fees" are tuition; "application
fee waivers" are not a tuition waiver. Rejected: "reimbursement of their PhD stipend" (no effect). Pool 610 -> 619 (816 correct,
89 wrong, 122 review on 1,112 decisions); Q 137 / 26 / 18 -> 138 / 22 / 20. The code was frozen here and set R (below) was
fetched from hosts no earlier set used; nothing on R was read before this freeze.

**Set R** (`tests/heldout_r/`, scored once on the frozen round-35 code, 2026-10-20): 239 pages fetched from hosts no earlier set used
(ministries, agencies, foundations, companies, professional associations, universities); only 14 were single-programme pages
(the rest were lists, home pages, news, portals or several awards, excluded with the reason recorded), so R holds 56
decisions and its figures carry a wide margin (roughly +/- 12 points). Round-35 code 37 correct / 6 wrong / 10 review (66% /
11% / 18%); round-33 and round-30 code identical; round-26 code 39 / 7 / 0. Leaving out the close calls (45 decisions): 31 / 5 / 8
(round 26: 33 / 5 / 0). Clean quotations on every claimed answer: 15/15. The six wrong claims: "Individuals who are not United
States citizens" (an ineligibility list item) read as an exclusion of US citizens; an opening date read as a deadline ("The
call opened on 24 August with a deadline on 21 September"); "awards must be used before August 1, 2027" read as a deadline;
an "open" cycle taken from that date; "receive financial support to aid their education" read as a stipend; and a
nationality list from a page whose associate-state sentence is cut off. R is development data from here: the first three
(and the stipend phrase) were fixed after R was scored (pool +9: N12, D7, F9 kept; the "must be used" date rule was rejected).
R shows no gain from rounds 30-35 over round 26 on this small sample; the gain is on the wrong-claim side only where the
pages are ambiguous (10 answers were sent to review instead of claimed). It does not contradict P and Q, whose sets are
5 to 5.5 times larger, but it is not evidence for them either.

### Round 36: set S (programme pages reached by following lists)

Sets Q and R showed that searching a domain for a named programme finds a single-programme page about 6% of the time. Set S
reverses the method (`tests/heldout_s/collect.py`): it opens the list, home and several-award pages that sets P, Q and R fetched but never
labelled, and follows, on the same site, the links whose text names a scholarship, fellowship, grant or award (robots.txt respected; a
host that carries a labelled page of any earlier set is skipped). 548 list pages gave 661 pages after the code was frozen; 30 were
single-programme pages with enough information to label (4.5%, mostly Fulbright commissions, foundations and named university
awards); the other 631 are excluded without a per-page reason (generic aid pages, lists, news, PDFs, near-empty pages or not reviewed).

Scored once on the frozen round-35 code: 120 decisions, **83 correct (69%) / 17 wrong claims (14%) / 13 sent to review (11%)**;
round-33 code identical; round-30 78 / 20 / 14; round-26 code 81 (68%) / 34 (28%) / 0. Without the close calls (95 decisions):
71 / 15 / 7 against 70 / 24 / 0 for round 26. Clean quotations on every claimed answer: 27/27. Per decision (frozen): eligibility
20 / 4 / 3, funding 13 / 3 / 10, cycle 25 / 5 / 0, deadline 25 / 5 / 0. This is the first set on which the later rounds roughly halve the wrong
claims without losing correct answers (R, with 14 programmes, could not show it; P and Q are consistent with it).

Six S labels were then adjudicated (`tests/heldout_s/adjudication.json`): four missed an application period lower on the page (Tokyo
Metropolitan, San Jose State, North Texas, Case Western), and two missed a stated nationality rule (Tokyo Metropolitan "non-Japanese
national", Fulbright Finland "open to U.S. students"). With them: 90 / 10 / 13, or 78 / 8 / 7 without the close calls. The adjudication
was written after the errors were seen, so it can only flatter the code; the frozen figures above are the headline. Remaining S errors: a "Hungarian citizens"
line from another scheme on the same page, "Swedish and American students" read as including the US, a yearly deadline without a year taken
from older dates, "room & board" not counted as living costs, and a mission sentence ("financial support to our international students") read as a
stipend and tuition. Two rules tried on these (dual-citizenship "may not apply", "room & board") changed nothing; one (mission sentence with "our ...
students") lost a correct answer and was rejected. S joins the development pool (K to S, 1,016 decisions: 719).

### Round 37: the risk gate (`audit._risk_gate`, `SCHOLAR_RISK_GATE=off|standard|strict`, default standard)

The precision of each kind of claim was measured on the 1,336 decisions of sets K to S: assistantship and fee-waiver funding classes 0 right
of 6; "not_announced" cycles 1 of 7; applicant deadlines with two or more dates 52%; tuition-only 58%; stipend-only 76%; "open to any
nationality" 67%; "upcoming" cycles 77%; single dates 83%; "partially funded" and "fully funded" 87-88%. Claims of the low-precision kinds are now sent
to review ("needs_review", reason recorded, value kept as unverified) instead of reported as known. Dates of earlier cycles that the record already
marks as past do not count toward "several dates". The gate is a reporting policy, not a rule change: it never alters what was extracted.

| Mode | Correct | Wrong claims | Sent to review | Not answered |
|---|---|---|---|---|
| off | 70.7% | 7.6% | 10.9% | 10.7% |
| standard (default) | 69.6% | 6.0% | 13.7% | 10.7% |
| strict | 65.6% | 4.4% | 19.2% | 10.7% |

(percent of all 1,336 decisions). The costs are 16 correct answers held back for 24 wrong claims removed in standard mode, and 69 for 45 in strict mode.
These figures are in-sample, because the thresholds came from the same data, so they will be somewhat optimistic on new pages; a fresh set is the check. The
pool utility rose from 719 to 740.5 in standard mode. Wrong claims per set fell, for example, P 7% -> 3%, S 8% -> 6% (standard), P 7% -> 2%, S 8% -> 5% (strict).
For a public site, strict is the setting that reaches the "under 5% of decisions" target on the pool, at the price of 19% of decisions going to review.

### Round 37 follow-up: out-of-sample check of the risk gate, and a discovery finding

**The gate on sets it was not chosen from.** The thresholds above were computed on K to S. Recomputed with only K to O as the training sets, the
claim kinds gated in `standard` and `strict` keep their low precision on P to S, which were not used to choose them: assistantship and fee-waiver
5 wrong of 5, "not_announced" 4 of 4, deadlines with several dates 7 of 9, stipend-only 4 of 12, tuition-only 3 of 5, "any nationality" 1 of 3,
"upcoming" 2 of 5. On P to S (628 decisions) wrong claims were 8.1% before the gate; standard brings them to about 5.6% and strict to about 4.0%
(correct 68.3% -> 68.0% standard, 65.6% strict). The extraction rules are still in-sample on these sets, so this is evidence about the gate, not a
fresh-set result.

**Country-by-country search finds mostly blogs.** A first attempt at set T searched, for each of 130 countries, in English and in the local
language, and fetched the first hosts it found: 959 pages, but the large majority were scholarship-blog, agent and aggregator pages ("Fully
Funded ... 2027", "Top 10 scholarships in ..."), which the agent must not treat as a source. The run was not labelled; its pages are kept local
(`tests/heldout_t/urls_search_run1.json`, not committed). A second run keeps only hosts that look like a government, an education body, a foundation or a
university (`OFFICIAL` in `tests/heldout_t/collect.py`).

### Round 39: old dates

Applicant dates more than two years old are references, not the deadline, unless their own sentence calls them the deadline ("application deadline",
"closing date", "apply by", "due", "applications closed"). Pool +11 (wrong claims -4: Pickering 2024, SSRC 2019, FAPESP 2019 and St. Thomas 2024 stop
being read as deadlines); the plainer version (any date older than two years) gained more (+18.5) but removed four correct "closed, last deadline
2013/2023/2020/2023" answers and was rejected. Also tried with no effect: a "campus/internal deadline" nomination step and "as of <date>" up to 35
characters before the date. After this round the pool reads 70.8% correct / 7.6% wrong / 10.9% review with the gate off, 69.7% / 5.9% / 13.7% in standard mode and
65.7% / 4.3% / 19.2% in strict mode. Many of the remaining wrong claims are label-policy differences rather than reading errors (for example "All nationalities
are welcome" read as "any" where the label says not stated), which is why the second labeller matters.

### Round 40: source registry from the lists the benchmark sets fetched

217 official list or portal pages that sets P, Q, R and S fetched but never labelled (and whose hosts carry no labelled page of any set) were
checked again (reachable, robots-permitted, page kind listing, opportunity or guidance) and added to `sources.json`: the registry grows from 111 to 328
sources and from 54 to 63 countries (197 universities, 10 government bodies, 10 foundations, mostly US because P was a US-university set). Hosts of labelled
pages were left out on purpose so the evidence-authority checks on every benchmark page are unchanged; the pool figures did not move (standard mode 743.5).
These are portal pages, not verified records: each still goes through discovery, extraction, verification and the risk gate. Wider cover outside the US
needs the curated per-region lists described in the plan.

## Round 41: set T (fresh country-search set), measured once

Set T was collected by country-by-country search of official hosts (university, ministry, agency, embassy, foundation, national
programme sites), 584 pages fetched on 2026-10-20, 40 single-programme pages labelled by hand (see
`tests/heldout_t/make_labels.py`; the 544 excluded pages stay local, only the 40 labelled pages are in the repository).
Code, labels and scorer were frozen before scoring; the code was scored once, with the standard and the strict gate.

| Gate | Wrong claims among answered (all labels) | Wrong claims, clear labels only | Sent to review |
|---|---|---|---|
| standard | 14.6% (20/137) | 12.7% | 23 |
| strict | 11.6% (15/129) | 10.4% | 31 |

The target (under 5%) is **not met** on a fresh country-search set; the in-sample figures (4.3%) and the P to S figures (about 4%)
did not carry over. Of the 15 strict wrong claims, about nine are real extractor bugs: "citizen of any country outside the UK"
read as include GB, "outside of New Zealand" read as include NZ, "UK first class honours degree" read as nationality GB,
"same conditions as Ukrainian citizens" read as include UA, and a cycle read as open from renewal or other-year dates. The rest
are close calls (domestic and international applicants on one page, a 25/75 tuition split, "contribute towards maintenance").
From now on T is development data. A new untouched set (U) is needed for the next honest figure.

## Round 42: set U (third fresh set), measured once

Set U was collected after the round-41 code was finished: country searches for programmes for students from each country and
for each country's university scholarships, every host of sets A to T left out. 556 pages fetched on 2026-10-21, 44
single-programme pages labelled by hand (`tests/heldout_u/make_labels.py`), code, labels and scorer frozen, scored once.

| Code | Wrong claims among answered | Clear labels only |
|---|---|---|
| round-33 rules (before the gate) | 10.3% (16/156) | |
| round-41 rules, no gate | 9.0% (14/156) | |
| round-41 rules, standard gate | 7.2% (11/152) | 5.9% (7/119) |
| round-41 rules, strict gate | 5.4% (8/147) | 4.3% (5/116) |

One label was wrong (u-qa-2 lists six countries lower on the page; `adjudication.json`); the extractor still missed Bosnia, so
the adjudicated figures are the same. The eight strict wrong claims: a webinar date read as a deadline, a cycle read as open
between two rounds, "rolling basis" (the label policy calls this not stated), a capped tuition award read as fully funded, a
"fully funded" page read as partial, and the Graz country list. With 147 answered decisions the 95% interval of 5.4% is
roughly 2.4% to 10%: the strict gate is near the 5% target on fresh pages but this does not yet prove it. From now on U is
development data.

## Round 43: set V (the agent's own registry pages), measured once

Set V is the first fresh set taken from the pages the agent itself reads: every source in `sources.json` was fetched and award
links on it were followed (501 pages, 2026-10-21). 86 single-programme pages were labelled by hand before any extractor ran;
code, labels and scorer were frozen and scored once. The Claude second reading (round 43) was not active (no model key yet).

| Code | Wrong claims among answered | Clear labels only |
|---|---|---|
| round-33 rules | 11.2% (35/313) | |
| round-42 rules, no gate | 10.8% (34/314) | |
| round-42 rules, standard gate | 9.2% (28/306) | 7.7% (20/260) |
| round-42 rules, strict gate | 7.2% (21/293) | 5.6% (14/250) |

Sets U and V together (strict gate): 29 wrong claims in 440 answered decisions, 6.6% (95% interval about 4.6% to 9.3%). The
target of under 5% is not met. The largest real error class on V is a host or destination country read as the applicant's
nationality ("countries outside the UK", "University of Nebraska", a UAE university page, "study in the UK"); the rest are
funding-class and cycle close calls. From now on V is development data.

## Round 44: second reading (Claude Haiku 5.5) and set W, measured once

**Second reading** (`scholarship_agent/ai_check.py`): a model reads the page on its own and gives the applicant's
nationality rule, funding class and deadlines with quotations. Every answered decision it reads differently is held for
review; the model never replaces a value, so it can only withhold answers. A cycle is not asked for (small models compare
dates with today badly); it is held together with a held deadline. A reader that finds no nationality rule does not hold
an exclusion (exclusions are often worded as fee rules). Enabled with `SCHOLAR_SECOND_READING=1` and the configured
provider (production stays Claude-only; a local Ollama model was used only for testing).

Development data (sets K to V, 509 pages, strict gate; policy chosen here):

| Reading | Wrong claims among answered | Correct answers | Utility |
|---|---|---|---|
| rules only | 6.19% (102/1648) | 1293 | 1011.0 |
| + Claude Haiku 5.5, hold every disagreement | 3.47% (54/1555) | 1248 | 1039.5 |
| + Claude Haiku 5.5, final policy | 3.52% (55/1563) | 1255 | 1048.0 |
| + local Qwythos 9B (sets K to O only) | 4.10% | | |

Claude cost: USD 0.20 for 507 pages (USD 0.0004 a page).

**Set W** (fifth fresh set; 426 pages from registry pages and country searches, 100 labelled; frozen before the checker
policy was final and before any W row was looked at). Rules-only results were recorded at freezing; the checker was then
finalised on development data only and run on W once (USD 0.04):

| Code on set W | Wrong claims among answered | 95% interval | Correct answers |
|---|---|---|---|
| rules, no gate | 16.3% (56/343) | | 255 |
| rules, standard gate | 13.9% (46/331) | | 253 |
| rules, strict gate | 8.3% (25/302) | 5.7–11.9% | 245 |
| rules, standard gate + Claude second reading | 7.2% (21/292) | | 239 |
| **rules, strict gate + Claude second reading** | **4.0% (11/276)** | 2.2–7.0% | 233 |

Set W is harder than U and V (more fellowships, research and US graduate-school pages). With the strict gate and the Claude
second reading, wrong claims are under 5% on a fresh set for the first time; the upper end of the interval is still above
5%, so the next fresh set should confirm it. The manifest of W hashes `ai_check.py` as it was at freezing; the final policy
differs in the exclusion rule above (decided on sets K to V), so the checker results come from `tests/decisions_check.py`
with the cached readings in `results/`.

## Round 45: rules from set W, checker variants, and set X, measured once

**Rules** (decided on sets K to W only): "UK and overseas students" is a fee status, not a country rule; "non-X applicants may
also be considered" is an allowance, not an exclusion; "Dual nationals are not eligible" names no country; a date after
"the week of" is an event; a date after "closed until" is when applications open (`_date_role`; two wrong
claims fewer on set W, no set worse). Tried and dropped: German "öffnet am" as an opening (no effect) and "closed, next
round to be announced" as not announced (one gained, one lost). Unit tests in
`tests/test_scholarship_round42.py` (class `TestRound45`).

**Checker variants** (development data only; cached readings, strict gate):

| Second reading | Sets | Wrong claims among answered | Correct | Held but right | Utility |
|---|---|---|---|---|---|
| rules only | K–O | 6.61% (38/575) | 460 | 75 | 346.5 |
| Claude Haiku 5.5, v1 prompt | K–O | 4.46% (24/538) | 437 | 98 | 340.0 |
| Claude Sonnet 5.5, v1 prompt | K–O | 4.41% (24/544) | 443 | 92 | 349.0 |
| Haiku and Sonnet, hold if either disagrees | K–O | 4.17% (22/528) | 429 | 106 | 332.0 |
| Haiku and Sonnet, hold if both disagree | K–O | 4.69% (26/554) | 451 | 84 | 357.0 |

A second prompt (fee-status and exclusion wording, stricter "fully funded") was slightly worse on K–W and was reverted; the
quotation check stays (a value whose quotation is not on the page cannot hold an answer). Sonnet reads about as well as Haiku
here at about 20 times the price (USD 1.32 for 182 pages), so the checker stays on Haiku.

**Set X** (sixth fresh set; 551 pages fetched on 2026-10-23: 320 from country searches, 39 award links from the agent's own
registry pages, 192 from a second country search with government and doctoral queries; every address of an earlier set and
every host labelled in sets T to W left out; 126 single-programme pages labelled blind and frozen before any page was
scored). Measured once:

| Code on set X | Wrong claims among answered | 95% interval | Correct answers |
|---|---|---|---|
| rules, no gate | 9.8% (43/437) | 7.4–13.0% | 291 |
| rules, standard gate | 8.0% (34/427) | 5.8–10.9% | 290 |
| rules, strict gate | 5.6% (23/409) | 3.8–8.3% | 283 |
| rules + Claude second reading, no gate | 2.3% (9/390) | 1.2–4.3% | 278 |
| rules, standard gate + Claude second reading | 2.5% (10/396) | 1.4–4.6% | 283 |
| **rules, strict gate + Claude second reading** | **2.1% (8/389)** | **1.0–4.0%** | 278 |

Clear decisions only (close calls left out): rules with the strict gate 4.6% (15/329), with the second reading 1.3% (4/315).
Claude cost: USD 0.05 for 126 pages. The second reading held 15 of the 23 wrong claims of the rules (dates read from an
age limit, a start date, a staff tenure date and a training period; a country list read from a list of US areas;
residence read as citizenship) and cost 5 right answers (283 to 278). Of the 8 wrong claims left, 5 are cycle states: the
reader is not asked for the cycle, which is held only together with a held deadline, so a cycle check is the next lever.

Sets W and X together, strict gate + second reading: 19 wrong of 665 answered (2.9%, 95% interval 1.8–4.4%). The accuracy
condition for public status (a fresh set of at least 100 pages, wrong claims at most 5% and the interval's upper end at most
7%) is met on set X. Still open for public status: a second labeller's agreement, a legal review of privacy and terms, and
login with encrypted user data. Set X is now development data (`tests/devpool.py`).

## Round 46: accounts and encryption, legal packet, second labeller, and a cycle check

**Multi-user service.** `accounts.py` (scrypt passwords, expiring sessions, lockout, password reset through an optional
SMTP server, consent records, account export and one-step deletion), `crypto.py` (AES-256-GCM encryption of every private
free-text field and the account e-mail, per-field binding, key rotation, production mode that requires keys from the
environment) and `web.py` (`serve`: an HTTP JSON API behind an HTTPS proxy, rate limits, security headers, every private
route bound to the caller's own profile). Tests: `tests/test_scholarship_round46.py`. A cross-tenant leak was fixed on the
way: `tracker.lessons` returned every user's outcomes.

**Legal readiness** (engineering material for counsel, not legal advice): `docs/scholarship-agent/legal/` holds a review
packet (records of processing, rights and the routes that serve them, security measures, processors and transfers,
children, breach procedure, questions for counsel) and draft privacy notice and terms in English and Indonesian.

**Label quality.** Every set-X label was compared with the cached independent Claude reading; where they differed on a
decision not marked as a close call, the page was read again in full. Five labels were wrong (requirement and coverage
lines the labeller's filtered view had not shown) and are recorded in `tests/heldout_x/adjudication.json`. Adjudicated set
X, strict gate: rules 5.4% (22/409), rules + second reading 1.8% (7/389). A human second labeller fills a 24-page form;
`tests/heldout_x/second_labeller.py` reports agreement and Cohen's kappa per decision.

**A cycle check in the second reading** (`SCHOLAR_SECOND_READING_STATUS=1`): the reader is also asked whether applicants
can apply as of today, and a different answer holds the cycle. Development data only (sets K to X, adjudicated labels,
strict gate; Claude Haiku 5.5 re-read 733 pages for USD 0.32):

| Second reading | Wrong claims among answered | Correct | Held but right | Cycle wrong | Utility |
|---|---|---|---|---|---|
| none (rules) | 5.17% (122/2358) | 1843 | 227 | 36 | 1485.5 |
| v1 prompt (round 44, the default) | 2.60% (58/2232) | 1781 | 289 | 28 | 1520.5 |
| new readings, status not used | 2.64% (59/2238) | 1786 | 284 | 27 | 1526.0 |
| new readings with the cycle check | **2.18% (48/2198)** | 1757 | 313 | 16 | 1504.5 |

The check removes 11 wrong claims and holds 29 right answers for review: a lower utility, so it stays off by default and
is the setting for a deployment that puts precision first. Asking the extra field did not change the other readings
(row 3 against row 2).

## Round 47: English first, catalogue search and details, destination countries, study levels

**Destination countries from the page's own words** (`destinations.py`). Until now `destination_countries` was the
country a search had asked for. On 80 development pages labelled by one person (`tests/destinations_labels.json`,
labels written before the extractor was run on a page; the extractor was built on the other 654 development pages):

| Method | Exact | Pages with a wrong country | Precision | Recall |
|---|---|---|---|---|
| search hint (`search:XX` only) | 14 | 7 | 0.46 | 0.07 |
| search hint passed down followed links (closer to live) | 16 | 25 | 0.32 | 0.14 |
| text extractor, blind run | 27 | 1 | 0.94 | 0.19 |
| text extractor after three fixes found on this sample | 27 | 0 | 1.00 | 0.19 |
| text, else the hint | 27 | 5 | 0.79 | 0.22 |

The hint is often the applicants' country or an unrelated search country, so a record now takes its destination from
the page text only (the hint is kept as a `searched_for:` tag). Recall stays low: 36 of the 80 pages name only the host
institution, and a fallback to the page's country domain was right 33 times and wrong 10 times (outbound programmes on
national sites), so it was not added. The fixed numbers are not blind; confirm on a fresh labelled sample.

**Study levels** (`tests/levels_eval.py`, all 720 labelled development pages; utility = exact − 2 × pages with an extra
level − 0.5 × pages with only a missing level). A level is read only from sentences that offer it: degrees the applicant
already holds or is finishing ("will have a bachelor's degree or equivalent", grades, copies of diplomas, final-year
students), exclusions, teaching duties, personal stories and short menu headings are skipped, and other senses of the
words are ignored ("exchange rate", "Academic Exchange Service", "master the", "Boston, MA", marketing "promotion").

| | Exact | Pages with an extra level | Pages with only a missing level | Utility |
|---|---|---|---|---|
| before | 328 | 289 | 103 | −301.5 |
| after | 429 | 164 | 127 | +37.5 |

Utility rose on every one of the 14 sets; the four decisions of `tests/devpool.py` are unchanged (they do not read
levels). The 21 rules were chosen on these same sets, so expect a smaller gain on new pages; no fresh set has level
labels yet.

**English first.** Titles and quotations from pages in other languages (56 of the 226 demo records) get an English
translation stored next to the original (`translate.py`, `translate` command; Claude through the usual paid-call
switches; each text paid once); the original stays the evidence and is one click away. Titles lose website names and
catalogue numbers (`clean_title`, conservative: a title that would become generic keeps its last part). On the demo
catalogue: 286 texts (55 titles, 231 quotations) of 56 records, 10 requests to Claude Haiku 5.5, USD 0.015; a spot check
of titles and quotations found faithful translations, but the model kept website names in titles, so `clean_title` also
runs on translated titles.

**Search and details** (`site.py`). Search matches every word against the title, provider and quotations, in the original and in
English, reads S1/S2/S3, master/doctorat and country names in English, Indonesian and other languages, filters by
destination, level, funding, open applications, closing within N days and the applicant's citizenship (programmes that
exclude it are hidden), and sorts by relevance or nearest deadline. The details add what the programme pays,
requirements, documents, every applicant date and how to apply, each with its quotation. A requirement the sentence
limits to some applicants ("except for MBA applicants, who require two years of work experience") and a document named
only in advice ("contact the advising centre for tips on your essay") are marked "check", not stated as rules.

## Round 48: more destinations, marked when inferred

**More destinations, marked when inferred.** When the text names no destination, a university's or college's own page
(ac.xx, edu.xx, US .edu, institution words in the host) takes the country of its web address, unless the page sends
people elsewhere (study abroad, overseas universities, travel grants), is only for that country's own citizens, or
relays another country's call (`destinations.host_destination`). On the 80 labelled pages: exact 27 → 56, wrong 0 → 1
(a Spanish school on a .edu address), recall 0.19 → 0.52; on the other 654 development pages, read by the same person
(not blind), it answers 192 with about 6 wrong. The demo catalogue goes from 50 to 135 of 226 records with a destination
(42 countries). Inferred destinations carry a question mark and a note that the page does not name the country.

## Round 49: a wider and more detailed catalogue, yearly deadlines, only programmes listed

**More official sources.** 161 sources were added to the registry: universities, national agencies and ministries in 72
countries, each checked on 2026-10-26 for robots permission and for a page that lists or describes scholarships.
Countries with a destination-specific official source: 97 → 124. A new adapter reads Campus France's scholarship
database (CampusBourses) through the JSON interface its own search page loads (`adapters/campusfrance.py`): 378
programmes for study in France with the applicant countries ("Location"), levels, subjects and "Apply before" date, and
from each programme's detail what it pays, the duration, documents, language and how to apply. Of the 376 new records:
eligibility 257, funding 302 (amounts 143), documents 255, duration 131, an application link 266.

**More detail from the structured sources.** DAAD detail pages are read section by section, without the contact
blocks, portal notes and the selector of 200 countries of residence (`adapters/daad.programme_page`). Of 148 DAAD
programmes: funding 19 → 135 (amounts 84), duration 10 → 66, documents 8 → 73, deadlines 14 → 60. Erasmus Mundus
consortium sites are read for every programme rather than the first 15, with up to four of the site's own pages
(scholarships and fees, admission and dates, the consortium); the study countries are those named beside the
consortium's universities, associated partners left out. Of 209 joint masters: study countries 0 → 100, funding 5 → 150
(amounts 73), dated deadlines 6 → 109, documents 4 → 142, eligibility 1 → 72 (831 requests, 97 failed or refused by
robots). An adapter that runs again replaces its own records instead of merging the old reading as conflicts.

**The live catalogue** (`data/catalog.db`, 2026-10-26, crawls still running): 409 → 1,610 records, 1,263 in search
results, study countries named on listed records 76. Shares of listed records with: funding 78%, an applicant deadline
59%, documents 58%, eligibility by nationality 51%, a destination 77% (at 626 records earlier the same day: funding 26%,
deadline 22%, documents 19%, eligibility 39%, destination 41%).

**Yearly deadlines.** "1 March and 1 September of each year", "Closing date ... 15 July of each year", "1 March for the
summer semester and 15 September for the winter semester" are kept as expected deadlines with their day
(`Deadline.recurs`), never as dated ones, and search results show the next such day as expected (`expected_deadline`). On the 735 development pages,
11 gain such a date (one tax-form date was kept out by requiring an applicant word); the decisions do not change, by
design: the deadline decision counts dated deadlines only.

**Rules (development pool of 14 sets).** "The fellowship is worth 3,600 EUR per month", "grant: 1,500 EUR per month" and
"base amount of up to 855 EUR per month" are read as stipends; a condition is not a negation ("if no guest room is
available, an accommodation allowance of 500 EUR per month will be paid"); "Applicants from China, India and Vietnam: APS
certificate ..." states a document, not who may apply. Utility 1469.5 → 1471.5 (+2 correct, no new wrong claim, no set
falls). Tried and rejected: "applications can be submitted at any time" as rolling (a labelled page says not stated),
a "Value" heading as a list of benefits (−5).

**Search results list programmes only** (`site.listed`). Records stay in the catalogue for review but are not listed
when the classifier could not place the page and its best guess is not an opportunity (news, events, research papers,
glossaries, hubs that list many programmes, guidance), when the page is an aggregator or catalogue page, for past
mobility projects, and for uncertain pages that state no term. Of 714 page-based records, 283 are left out. In a
sample of 30 each, judged from the title and web address, 26 of the left-out records were not programmes (4 were: two
JSPS fellowships, a Beihang scholarship and the P.E.O. peace scholarship) and 21 of the listed ones were.

**Second reading of the live catalogue.** The new `check` command fetches each page-based record's page again and asks
Claude Haiku 5.5 for its own reading (records from structured datasets are left out): 455 records read, 10 pages
unreadable, $0.17. 88 records have a decision held for review (eligibility 29, funding 41, deadline 30, cycle 17).

**Speed.** Reading a stored record 1.56 → 0.20 ms (field types are resolved once), and a new record is matched against
the catalogue's titles rather than whole records, which made long crawls CPU-bound before.

## Round 50: the crawl finished overnight, tighter listing, a sturdier check pass

The registry crawl, the 161 new sources and a first pass of the country search ran overnight: 1,610 → 3,716 records,
106 study countries named on listed records. The search stopped after 123 of 1,848 queries when the upstream engines
throttled the local SearXNG; it is resumable (`strategy-run --resume`). Search results now also leave out pages named
only by an office or topic ("Financial Aid | Example College", "Scholarships", "Login", "About Us") even when the
classifier called them programme pages: 2,588 → 2,528 listed; "Scholarship - Vietnam High Achievers" names a
programme and stays. The `check` pass stopped at the first request the model did not answer; a single failure is now
skipped and three in a row end the run. `data/crawl/nightly.sh` (not committed) runs one pass of search, refresh,
registry crawl and second reading (at most $0.20).
