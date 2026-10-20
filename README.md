# Scholarship Intelligence Agent

*Find the funding. Check the source. Know if you qualify.*

An AI-powered agent for global scholarship discovery and verification. It searches in many languages, backs every value with a quotation from the official source, analyses eligibility and funding, and tracks application deadlines. It runs on your own machine, keeps your data local, and refuses to claim anything an official page does not say.

> This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by any scholarship provider, university, government or AI company named in this repository. Always confirm an opportunity on the provider's own website before you apply.

## Why this exists

Scholarship information is scattered across thousands of university pages, ministry portals, foundation sites and PDFs, in dozens of languages. Many of the best programmes are small, local, or open only to applicants from a few countries, and aggregator sites often copy outdated deadlines or "fully funded" claims that the official page never makes.

This agent treats every opportunity as a claim to be checked:

- **Who may apply?** Nationality, residence, study level, field, age, grades, language.
- **What is actually paid?** Tuition (full or partial), stipend, travel, insurance, housing. The agent records each part separately; "fully funded" is never assumed.
- **When do you apply?** Applicant deadlines, kept apart from openings, nominations, document dates, payment dates, notification dates and last year's dates.
- **Where does it say so?** A verbatim quotation from the official page for every value. If the evidence is missing, the agent says "not stated" or sends the decision to review instead of guessing.

## What it does

```
 discover            verify              match / rank            plan / prepare           track
     |                  |                      |                        |                     |
     v                  v                      v                        v                     v
 registry +        re-read the          eligibility for         requirements matrix,   checklist, deadlines,
 multilingual      official page,       your profile, funding   timeline, CV, essays,  reminders (.ics),
 web search,       quote-check every    class, transparent      statements and         status, outcomes
 adapters          value, keep          weighted ranking        reviewer feedback
 (DAAD, Erasmus    conflicts
 Mundus, EURAXESS)
```

- **Discovery:** a registry of 111 official sources, adapters for DAAD, Erasmus Mundus and EURAXESS, published sitemaps, and an optional self-hosted SearXNG search. The search runs a country-by-country strategy across 231 countries and territories, including domestic-only and local-language queries, with a vocabulary for 42 languages.
- **Extraction:** a structured `Opportunity` record. Each field carries an `Evidence` record: value, source URL, verbatim sentence, retrieval time, source authority and status.
- **Verification:** only an official page (programme, university, funder, government or official feed) can confirm a value. Aggregators and search results are leads only. When sources disagree, all values are kept as conflicts.
- **Applicant side:**
  - a private profile with confirmed and inferred facts kept apart
  - an eligibility decision with reasons
  - a funding coverage estimate
  - an explained ranking (not a probability of winning)
  - a requirements matrix and a missing-documents list
- **Documents:** drafts and reviews of academic CVs, statements of purpose, motivation letters, scholarship essays and research proposals. Drafts are built from confirmed facts only, and gaps are marked `[YOU WRITE: ...]`. The reviewer flags unsupported claims and inconsistencies. The agent never writes a recommendation letter as the referee.
- **Tracking:** application status, checklist, deadlines, reminders exported as an `.ics` file, and outcomes. Nothing is ever sent, submitted or emailed for you.

## Does it work? (honest numbers)

Every rule change is measured against frozen test sets. Each set holds official programme pages fetched from hosts never used before, labelled by hand with a quotation for each decision, and frozen (hash-checked) before scoring. Each set is used once as a test set; after that it becomes development data. Four decisions are scored per programme: eligibility by nationality, funding class, application cycle, and applicant deadline.

| Fresh test set | Decisions | Correct, answered without review | Wrong claims | Sent to review |
|---|---|---|---|---|
| Set M (round 28) | 160 | 64% | 18% | 10% |
| Set N (round 29) | 156 | 62% | 18% | 13% |
| Set O (round 30) | 120 | 58% | 14% | 14% |
| Set P (round 31, universities) | 236 | 64% | 13% | 16% |
| Set Q (round 33, governments, foundations, companies) | 216 | 60% | 17% | 8% |
| *Round-26 baseline on set Q* | 216 | 58% | 25% | 0% |
| Set R (round 35, mixed funders; only 14 programmes, wide margin) | 56 | 66% | 11% | 18% |
| Set S (round 36, programme pages reached from lists) | 120 | 69% | 14% | 11% |
| *Round-26 baseline on set S* | 120 | 68% | 28% | 0% |

- The remaining decisions are honest "not stated" answers where the label has a value.
- Every decision the agent reports as known carries a clean quotation from the programme's own page (37/37 on set O, 45/45 on set P, 66/66 on set Q).
- **Weakest areas:** the funding class when the award is a cash amount or a tuition discount tier (university pages, set P), and the applicant deadline on funder pages that list a whole timeline (set Q: 10 wrong deadlines out of 54). Wrong claims are 13-17% of decisions; the target for a public site is under 5%.
- **Claude-assisted extraction** (`tests/decisions_ai.py`) adds a few correct answers on top of the rules without adding wrong claims (+5 correct on 276 decisions, $0.80); every model answer is quote-checked before it counts. On set P it added dates and cycle states, not funding classes ($0.66).

- **Risk gate:** claim kinds whose measured precision is low (assistantship and fee-waiver funding, "announcement pending" cycles, deadlines with several dates; in `SCHOLAR_RISK_GATE=strict` also tuition-only and stipend-only funding, "any nationality" and "upcoming") are shown as unverified and sent to review. On the development pool this brings wrong claims from 7.6% to 6.0% (standard) or 4.4% (strict) of decisions, at the cost of more answers going to review; confirm on a fresh set before relying on it.

See [docs/scholarship-agent/EVALUATION.md](docs/scholarship-agent/EVALUATION.md) for the method and the full history.

## Prerequisites

- Python 3.10 or newer. The core uses the standard library only; there is no install step.
- Optional: [Docker](https://www.docker.com/) to run a local [SearXNG](https://github.com/searxng/searxng) instance for free web search (`deploy/searxng/start.sh`, bound to localhost).
- Optional: `pypdf` for better PDF reading.
- Optional: an Anthropic API key for Claude-assisted extraction. It is **off by default**: every request is a dry run (estimated, not sent) until you set `ANTHROPIC_ALLOW_PAID=1` and give it budgets greater than zero.
- Optional: [Claude Code](https://claude.com/claude-code) to use the slash commands (`/discover`, `/verify`, `/match`, ...). The CLI works without it.

## Quick start

```bash
git clone https://github.com/<you>/Scholarship-Intelligence-Agent.git
cd Scholarship-Intelligence-Agent

# 1. Your profile (stored locally in ./data/private, never committed)
python3 -m scholarship_agent setup --file my_profile.json

# 2. Find opportunities (registry only; add search below)
python3 -m scholarship_agent discover --countries DE,NL,SE --levels master --no-search

# 3. Check, compare and plan
python3 -m scholarship_agent rank
python3 -m scholarship_agent verify <id>
python3 -m scholarship_agent match <id>
python3 -m scholarship_agent funding <id>
python3 -m scholarship_agent plan <id>

# 4. Prepare and track
python3 -m scholarship_agent prepare <id>
python3 -m scholarship_agent deadlines
python3 -m scholarship_agent reminders --ics deadlines.ics
python3 -m scholarship_agent report
```

Every command prints JSON. Errors exit with code 1 and `{"error": ..., "type": ...}`.

### Free web search (optional)

```bash
deploy/searxng/start.sh                 # local SearXNG on 127.0.0.1:8080
export SEARCH_PROVIDER=searxng SEARXNG_URL=http://127.0.0.1:8080
python3 -m scholarship_agent search-check
python3 -m scholarship_agent strategy-plan --countries ID,VN
python3 -m scholarship_agent strategy-run --countries ID,VN
python3 -m scholarship_agent coverage
```

## Commands

| Area | CLI (`python3 -m scholarship_agent ...`) | Claude Code |
|---|---|---|
| Profile and privacy | `setup`, `profile`, `export-data`, `delete-data --yes` | `/scholar-setup` |
| Discovery | `discover`, `scrape <url>`, `adapter daad\|erasmus_mundus\|euraxess`, `strategy-plan`, `strategy-run`, `coverage`, `sources --check` | `/discover`, `/scholar-scrape`, `/sources` |
| Verification | `verify <id>`, `refresh`, `catalog-audit`, `show <id>`, `search` | `/verify` |
| Fit | `match <id>`, `funding <id>`, `rank` | `/match`, `/scholar-rank` |
| Planning | `plan <id>`, `documents <id>`, `deadlines`, `reminders` | `/plan`, `/documents`, `/deadlines` |
| Documents | `prepare`, `cv <id>`, `essay <id>`, `brief`, `save-draft`, `review <id>`, `export` | `/prepare`, `/cv`, `/essay`, `/review` |
| Tracking | `track`, `outcome <id> <result>`, `report` | `/track`, `/scholar-outcome`, `/report` |
| Quality | `quality`, `heldout`, `compare`, `stats`, `ai-usage` | |

Full reference: [docs/scholarship-agent/README.md](docs/scholarship-agent/README.md). Search setup: [SEARCH.md](docs/scholarship-agent/SEARCH.md).

## How accuracy is protected

- **Source authority, strongest first:**
  1. official programme page
  2. official university or funder page
  3. government or agency page
  4. official catalogue or structured feed
  5. trusted secondary source
  6. aggregator or general search result
  7. unverified lead

  Only levels 1 to 4 can confirm a value.
- **Quote checks:** a value is reported only if its quotation is on the programme's own page, states the value, and names no other programme. Otherwise the decision goes to review.
- **Date roles:** each date is typed by the words around it: application deadline, opening, nomination, document, payment, notification, programme stay, another programme's date, or an old reference. Only applicant deadlines with a year are reported as deadlines. Past deadlines are never projected forward.
- **Nationality by scope:** negation ("non-U.S. citizens", "not an Australian citizen"), exclusions ("outside the EU/EEA and Switzerland"), groups (EU, EEA, EFTA), conditions and definitions are read per clause. Fee status, domicile and residence are kept apart from nationality.
- **Funding by component:** "fully funded" needs documented full tuition *and* a living stipend or allowance. A stated discount, share or cap means partial funding.
- **Uncertainty is explicit:** missing is reported as "not stated", never as "not required". Unverified evidence can give `UNCERTAIN`, never `INELIGIBLE`.
- **Untrusted content:** page text is pattern-matched, never followed. Text aimed at AI systems is flagged.
- **Polite crawling:** robots.txt is honoured (fail-closed), with per-host rate limits and backoff. A site that refuses automated clients is marked for manual checking and never worked around.

## Privacy and safety

- **Separate stores:** the public catalog (`data/catalog.db`) and private applicant data (`data/private/`, file mode 0600) are kept apart and are both gitignored. `export-data` and `delete-data` cover everything private.
- **No outgoing messages:** nothing leaves your machine except page fetches, search queries and, only if you enable them, Claude requests.
- **API keys:** keys are read from your shell environment only and never written to files or logs. `.env.example` lists every setting with empty values. Never commit a real key.
- **Paid calls:** Claude usage is budget-capped per run and across runs; `ai-usage` shows tokens and estimated cost. A misconfigured provider is an error; the agent never silently switches provider.

## Building on it (API)

The CLI and the Claude Code commands are thin callers of one service class, `scholarship_agent.service.ScholarshipService`. A future multi-user website or REST API can call the same methods. Each takes plain arguments and returns a JSON-serialisable dict with a `schema_version`. One data directory per tenant keeps users apart. See [docs/scholarship-agent/API.md](docs/scholarship-agent/API.md) for suggested routes.

## Project layout

```
scholarship_agent/      the agent (models, extract, evidence, verify, eligibility, funding, ranking,
                        planning, documents, tracker, search, strategy, adapters/, service.py, cli.py)
docs/scholarship-agent/ reference, search setup, evaluation method, API boundary
deploy/searxng/         local search engine (localhost only)
tests/                  unit tests, regression examples, frozen evaluation sets (heldout_*/)
.claude/                Claude Code skill and slash commands
```

## Development

```bash
python3 -m unittest discover -s tests -t .   # unit tests and regression examples
python3 -m scholarship_agent quality         # extraction on labelled fixtures
python3 tests/devpool.py                     # decision scores on all development sets at once
```

A rule change is kept only when it improves the pooled development score without lowering it on any set. It is then judged once on a new frozen test set. Passing the regression examples is not counted as evidence that a rule generalises.

## Roadmap

- **Dates:** award-term and tenure dates, information sessions and sub-track deadlines. Uncertain deadlines should be sent to review.
- **Eligibility:** exclusion lists ("not open to students from ... (A, B, C)") and two-nationality rules ("Spanish or Portuguese").
- **Claude-assisted extraction** evaluated on the decision benchmarks, with quote checks kept.
- **A rubric benchmark** for the quality of generated application documents.
- **A web API and multi-user website** on top of `ScholarshipService`.

## License

Released under the [MIT License](LICENSE). Pages stored under `tests/heldout_*/pages/` are copies of public official pages kept only for reproducible evaluation; their content belongs to the original publishers.
