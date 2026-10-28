# Scholarship Intelligence Agent

A global scholarship research and application agent built on this repository's
Claude Code workflow. It discovers funding opportunities, extracts them into a
structured, evidence-backed record, verifies them against official sources,
evaluates an applicant's eligibility, analyses funding, ranks opportunities
transparently, drafts and reviews application documents, and tracks
checklists, deadlines and outcomes.

Claude Code commands: `/scholar-setup`, `/discover`, `/verify`, `/match`,
`/scholar-rank`, `/plan`, `/prepare`, `/deadlines`, `/track`, `/report`, ...

## Quick start

```bash
python3 -m scholarship_agent setup --file my_profile.json      # or /scholar-setup in Claude Code
python3 -m scholarship_agent sources --check                    # test the source registry
python3 -m scholarship_agent discover --countries DE,HU --levels master --no-search
python3 -m scholarship_agent rank
python3 -m scholarship_agent verify <id>
python3 -m scholarship_agent match <id>
python3 -m scholarship_agent plan <id>
python3 -m scholarship_agent prepare <id>
python3 -m scholarship_agent deadlines
python3 -m scholarship_agent report
```

Python 3.10+ and the standard library only. No install step, no paid service
required. Every command prints JSON.

## Commands

| Claude Code | CLI | Does |
|---|---|---|
| `/scholar-setup` | `setup`, `profile`, `export-data`, `delete-data --yes` | applicant profile (confirmed vs inferred facts) |
| `/discover` | `discover` | registry sources + optional web search -> extract -> dedup -> persist |
| `/scholar-scrape` | `scrape <url>...` | ingest specific permitted pages |
| `/verify` | `verify <id> [--official-url]`, `refresh` | confirm claims on the official page; keep conflicts |
| `/scholar-rank` | `rank [--weights]` | weighted, explained ranking; hard failures excluded |
| `/match` | `match <id>`, `funding <id>` | eligibility decision with evidence; funding class and estimate |
| `/plan` | `plan <id>` | requirements matrix + dependency-ordered timeline |
| `/prepare` | `prepare`, `brief`, `save-draft`, `export` | CV, briefs, drafts, review, versions, .pdf and .docx |
| `/essay` | `essay <id> --kind` | essay brief, draft, review |
| `/cv` | `cv <id>` | tailored academic CV from confirmed facts |
| `/documents` | `documents <id>` | readiness audit |
| `/deadlines` | `deadlines`, `reminders [--ics]` | confirmed / expected / unknown / historical; reminders |
| `/track` | `track [<id> --status --item]` | application state machine and checklist |
| `/review` | `review <id>` | pre-submission blockers |
| `/scholar-outcome` | `outcome <id> <result>` | result + lessons |
| `/report` | `report` | structured overview |
| `/sources` | `sources [--check] [--add]` | registry health, freshness, coverage gaps |
| | `show <id>`, `search` | inspect the catalog |
| `/discover` | `adapter daad|erasmus_mundus|euraxess [--details]`, `euraxess-import <file> --url` | dedicated structured-source adapters |
| `/discover` | `search-check`, `strategy-plan`, `strategy-run`, `coverage`, `run-report` | live search setup test, country-by-country search, coverage, found/retrieved/verified report (see `SEARCH.md`) |
| `/verify` | `refresh --plan`, `refresh` | prioritised re-verification (upcoming deadlines, conflicts, past-cycle-only, stale, incomplete) |
| | `quality`, `heldout --set a|b [--ai]` | accuracy on dev fixtures / held-out real pages (see `EVALUATION.md`) |
| | `ai-usage` | AI provider, paid vs dry-run requests, tokens, estimated cost |
| | `compare --set a|b [--providers rules,anthropic]` | rules vs Claude on the same pages and scoring; Claude is scored only when it actually ran |

Errors: exit 1 with `{"error": ..., "type": ...}` (unknown opportunity, invalid
status transition, missing profile). Argument errors exit 2.

## Configuration

| Variable | Needed for | Notes |
|---|---|---|
| `SCHOLAR_DATA_DIR` | optional | default `./data` (gitignored). `catalog.db` public data, `private/private.db` applicant data (0600). |
| `SEARCH_PROVIDER` (or `SCHOLAR_SEARCH_PROVIDER`) | optional | `searxng`, `brave` or `none`. Default: first configured. |
| `BRAVE_SEARCH_API_KEY` | web search via Brave | Brave Search API. Paid plans; check the current free-tier terms and quota before relying on it. |
| `SEARXNG_URL` | web search via SearXNG | `http://127.0.0.1:8080` with `deploy/searxng/start.sh` (see SEARCH.md). No per-query cost self-hosted. |
| `SCHOLAR_USER_AGENT` | optional | identify your deployment to sites. |
| `AI_PROVIDER` (or `SCHOLAR_LLM_PROVIDER`) | AI-assisted extraction | `anthropic` or `gemini` (paid cloud, see below), `ollama` (local), `openai_compat`, or `none`/unset = deterministic only. A misconfigured provider is an error; the agent never switches to another provider by itself. |
| `OLLAMA_MODEL` (or `SCHOLAR_LLM_MODEL`) | `ollama` | e.g. `qwythos-hermes:latest`. |
| `ANTHROPIC_API_KEY` | `anthropic` | Your key, from your shell only. The generic `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` are ignored on purpose. |
| `ANTHROPIC_MODEL` | `anthropic` | default `claude-opus-5-5`; any current model id works (set `ANTHROPIC_PRICE_*_PER_MTOK` for ids without a built-in price). |
| `ANTHROPIC_ALLOW_PAID` | `anthropic` | must be `1` for any paid request. Unset = dry run: each request is estimated (tokens, USD) and skipped. |
| `ANTHROPIC_MAX_REQUESTS_PER_RUN`, `ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN`, `ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN`, `ANTHROPIC_MAX_ESTIMATED_COST_USD` | `anthropic` | per-process budgets, default 0. A request whose worst case would cross any of them is not sent. |
| `ANTHROPIC_MAX_TOKENS`, `ANTHROPIC_EFFORT`, `ANTHROPIC_TIMEOUT_SECONDS`, `ANTHROPIC_MAX_RETRIES`, `ANTHROPIC_MAX_CONCURRENCY` | optional | per-request output cap (4000), effort (`low`), timeout (120 s), retries on 429/5xx (3), parallel requests (2). |
| `GEMINI_API_KEY` | `gemini` | Your Gemini Developer API key (aistudio.google.com). `GOOGLE_API_KEY`, Vertex AI and other Google credentials are ignored on purpose. |
| `GEMINI_MODEL` | `gemini` | default `gemini-3.8-flash` (stable, 2026-10); prices for current models are built in, others need `GEMINI_PRICE_*_PER_MTOK`. |
| `GEMINI_ALLOW_PAID`, `GEMINI_MAX_REQUESTS_PER_RUN`, `GEMINI_MAX_INPUT_TOKENS_PER_RUN`, `GEMINI_MAX_OUTPUT_TOKENS_PER_RUN`, `GEMINI_MAX_ESTIMATED_COST_USD` | `gemini` | same rules as Anthropic: dry run unless `1`, budgets default 0, kept separate per provider. |
| `GEMINI_MAX_TOKENS`, `GEMINI_THINKING_LEVEL`, `GEMINI_TIMEOUT_SECONDS`, `GEMINI_MAX_RETRIES`, `GEMINI_MAX_CONCURRENCY` | optional | output cap (4000), thinking level (`low`), timeout (120 s), SDK retries on 408/429/5xx (3), parallel requests (2). |
| `OLLAMA_HOST` | optional | default `http://localhost:11434`. Start the server with `ollama serve`. |
| `SCHOLAR_LLM_BASE_URL`, `SCHOLAR_LLM_API_KEY` | `openai_compat` | endpoint and key. Never read from any other variable. |
| `SCHOLAR_LLM_TIMEOUT` | optional | seconds per model call (default 600). |

All of these are listed in `.env.example`. Claude usage: `python3 -m scholarship_agent ai-usage` shows paid and
dry-run requests, tokens and estimated cost (list prices; the Anthropic Console is authoritative). Analysed
pages are cached by model + prompt + page text, so an unchanged page is never paid for twice. Model readings are
quote-checked like every AI reading and stay `extracted_unverified`; only verification against the official
page can confirm a value.

Keyless discovery: besides the registry pages, `discover` reads the sites'
own published sitemaps (robots.txt `Sitemap:` lines or `/sitemap.xml`) and
follows scholarship-looking URLs on the provider's official domains
(`--no-sitemaps` to turn off). PDF calls are read with pypdf when installed,
otherwise with a built-in reader for simple PDFs. When Python's TLS check fails
on a server with an incomplete certificate chain, the request is repeated with
the system `curl`, which still verifies certificates.

`python3 -m scholarship_agent quality [--ai | --ai-only]` scores extraction
against the labelled fixtures; `python3 -m scholarship_agent stats` reports how
complete the stored records are.
| `data/sources.local.json` | optional | your own sources (same shape as `scholarship_agent/sources.json`). |
| `data/ranking_weights.json` | optional | ranking weight overrides. |

Without a search provider, discovery runs from the source registry only, and
reports that it did.

## How accuracy is protected

- **Provenance.** Every extracted field carries an `Evidence` record: field,
  value, source URL, source type, source authority, the verbatim sentence it came
  from, retrieval time, verification time, status, confidence, extraction method
  (`rules`, `ollama`, `anthropic`, `structured`), scholarship cycle and validation
  warnings (why the quote may not substantiate the value).
- **Source authority** (`evidence.py`), strongest first:
  1 official programme page, 2 official university / funder page, 3 official
  government or agency page, 4 official catalogue or structured feed, 5 trusted
  secondary (e.g. another university relaying an external award), 6 aggregator
  or general search result, 7 unverified lead. Only 1-4 can confirm a value.
  Aggregator listings are not stored as records: the agent follows their links
  to the provider. Records keep `source_authority`, `discovered_authority`
  (where they were first found) and a plain-language `verification_reason`.
- **What "confirmed" means.** A value is `officially_confirmed` only when a
  level 1-4 page, re-read at verification, contains its quotation verbatim, the
  quotation states the value (the date, amount, score or countries), and for
  deadlines: the date is the applicant's (not an institution's, an event's or an
  open day), it applies to this programme (several programmes on one page need
  the quote to name it), its cycle is current and the date has not passed.
  An official page alone confirms nothing; re-extracting the same page is not
  proof. Past deadlines are never projected to the next year.
- **Status vocabulary.** `officially_confirmed`, `extracted_unverified`,
  `historical`, `estimated`, `conflicting`, `unknown`, `source_unavailable`.
- **Official sources win.** A source counts as official when its domain is in
  the registry's `official_domains` for that provider, or is a government /
  academic / intergovernmental domain. Aggregators and search hits are leads.
  A non-official page can suggest a deadline but never confirm one.
- **Missing is not "not required".** An absent language requirement is
  reported as unknown with "absence is not a waiver". An MOI route is surfaced
  only when the source documents one.
- **Conflicts are kept.** When sources (or two fetches of the same page)
  disagree, both values are kept in `conflicts` and the record is `conflicting`.
- **Dates.** Each date in a sentence is typed by its own clause: applicant
  closing date, opening, institutional (verification or nomination by
  universities/officials), event (results, interviews, open days), rolling, or
  not yet published; country-specific dates keep `scope: country` and
  `applies_to`. Approximate wording ("usually early February") is stored as an
  expected, unconfirmed deadline with no date. Ambiguous `03/04/2027` is stored
  as unknown. Past dates become historical; changed dates go to
  `deadline_history`.
- **Eligibility.** A mismatch backed only by unverified evidence gives
  `UNCERTAIN`, never `INELIGIBLE`. Inferred applicant facts never count as proof.
- **Funding.** `fully_funded` needs documented full tuition *and* a documented
  stipend/allowance. Estimates compare one currency unless you supply a rate.
- **Ranking** is a weighted sum with a reason per component. It is not a
  probability of winning.
- **Documents.** Drafts use confirmed facts only. Gaps become `[YOU WRITE: ...]`.
  The reviewer flags limits, missing topics, unsupported numbers/names/claims,
  cross-document inconsistency and placeholders. No recommendation letter is
  ever written as the referee; only a briefing pack for them.
- **Untrusted content.** Page text is only pattern-matched, never followed.
  Text aimed at AI systems is flagged. Briefs mark opportunity text untrusted.
- **Politeness.** robots.txt (the repo's RFC 9309 parser, fail-closed),
  per-host rate limit, retry with backoff on 429/5xx/network errors, and no
  retry or disguise on 401/403. Only HTML/text/XML/JSON is parsed.
- **Privacy.** Public catalog and private applicant data are separate files;
  both are gitignored. `export-data`
  and `delete-data --yes` cover everything private. Nothing is ever sent,
  submitted or emailed; reminders go to the console or an `.ics` file.

## Data model

`scholarship_agent/models.py`: `Opportunity` (id, title, provider, URLs,
destinations, levels, disciplines, `NationalityRule`, GPA/age/work/supervisor
requirements, `LanguageRequirement`s, MOI policy, `FundingComponent`s,
duration/renewal, `Deadline`s with kind/certainty/time zone/cycle,
`RequiredDocument`s with prompt/limits/translation/certification, selection
criteria, `Evidence`, verification status, uncertainties, conflicts),
`Profile` (citizenships, residence, DOB, `Education`, `TestScore`,
`Experience`, preferences, documents held, inferred facts), and the enums for
statuses. Storage (`store.py`, SQLite, versioned migrations): providers,
institutions, opportunities, deadlines, deadline history, verification
records, source state, page cache, search jobs, ingestion results; and
privately: profiles + history, applications, status history, checklist items,
documents + versions, reminders, outcomes.

## Implementation status (2026-10-17, round 7: Claude only)

| Capability | State |
|---|---|
| Live search (SearXNG / Brave) | local SearXNG via `deploy/searxng` (official image, localhost only); pagination, throttling, retries, key-safe errors, query log and cache, spam/irrelevant-result filter, engine statistics; **live-run on 10 countries** (below). Brave adapter untested live (no key) |
| Country-by-country strategy | all 231 countries x 10 query categories incl. domestic-only and local-language queries; coverage of countries configured vs searched; incremental via query cache; tested offline |
| DAAD adapter | published static dataset (148 programmes, per-origin deadlines, origin countries, applicant groups) + optional detail pages; live-run |
| Erasmus Mundus adapter | EACEA RSS + catalogue pages (217 entries; joint masters vs legacy projects) + optional consortium sites; live-run |
| EURAXESS adapter | offers are disallowed by robots.txt: only allowed Worldwide pages (leads) + import of user-saved offer pages; live-run |
| Extraction | deadline tables / label lines / ranges / in-sentence years, min vs max age with preference and child guards, nationality headings and demonyms, award amounts incl. K suffix, PDFs with per-font ToUnicode maps, gzip pages; verbatim evidence for every value |
| AI-assisted extraction | **Claude is the active provider** (`AI_PROVIDER=anthropic`, official `anthropic` SDK); it fills gaps the rules leave (deadlines, nationality, residency, levels, fields of study, provider, cycle, GPA/age/language, funding components incl. living allowance, accommodation, insurance, travel, documents, essay prompts) and reports page conflicts for a human; every value is quote-checked, model deadlines are never `confirmed`, and only verification against an official page confirms anything. Dry run by default, budgets 0, page cache, usage ledger. Implemented and tested with mocks; **not yet evaluated live** (no API key). Gemini and Ollama code kept but inactive |
| Verification | re-reads every official page a record's evidence came from; structured datasets keep their own status; field-level vs record-level reported separately |
| Freshness | prioritised refresh plan (upcoming deadlines, conflicts, past-cycle-only, stale, incomplete), configurable intervals |
| Reporting | `run-report`: provider/config, queries and countries, pages retrieved/failed, unique records, duplicates, record- and field-level verification, missing-field rates, runtime |
| Accuracy | `EVALUATION.md`: held-out set A (30 real pages) and independent set B (13) |

See `EVALUATION.md` for accuracy.

### Round 5 live re-run, 2026-10-17 (same 10 countries and queries, rules only, no paid calls)

Counted separately, never combined: 262 discovered leads; 42 records, of which 20 have an official source
(16 programme pages, 4 provider pages), 2 trusted secondary, 20 aggregator or unclassified search results;
13 officially verified programmes; 3 confirmed current deadlines (all three correct by their quotations:
Melbourne Human Rights 31 Oct 2026, Indian NSP student closing 31-10-2026, Sheffield Hallam 1 Nov 2026);
0 confirmed nationality rules; 13 confirmed funding coverage; 3 conflicting; 18 with flagged values; 8 with
outdated cycles only; 12 from aggregators, 1 of them confirmed on the provider's page; 10 aggregator listings
skipped as leads. Of 350 evidence items, 102 confirmed and 42 carry validation warnings; no confirmed item
carries a warning. Re-verifying the round 4 records with this code: 2 confirmed current deadlines, both correct
(round 4: 2, one wrong).

### Live SearXNG run, 2026-10-17 09:47-09:57 UTC (scratch data, rules only, no paid calls)

10 countries (ID, KE, BR, DE, JP, EG, VN, MX, FR, TR), 4 queries each (government, university, citizens-only,
local language; Kenya's 4th was research), 1 result page of 10 per query, at most 3 fetches per query.

| Stage | Result |
|---|---|
| Queries / errors | 40 / 0; every country searched |
| Engines that returned results | google cse 299, bing 101 (brave, qwant suspended; duckduckgo SSL; wikidata timeout) |
| URLs returned / new after dedup / on an official-looking domain | 400 / 343 / 122 |
| Dropped before fetching | 71 (53 no funding word, 15 spam or adult domains, 3 IP-address hosts) |
| Pages fetched / failed | 81 / 31 (most failures: robots.txt blocks or unreachable robots.txt, 403s; not bypassed) |
| Skipped as not opportunities | 32 (17 irrelevant, 11 news, 4 guidance) |
| New records / duplicates merged | 47 / 9 |
| Re-checked against an official page | 14 records |
| Record status | 8 confirmed (at least one key field), 7 conflicting (5 are aggregator pages listing several programmes), 32 unverified (not an official page) |
| Field level confirmed: current deadline / nationality / funding | 2 / 6 / 9 (a manual check found 1 of the 2 deadlines wrong) |
| Runtime / memory | 501 s search+fetch, 63 s verification; 46 MB peak |

By my manual reading of the 47 records: about 30 are on the provider's or a government's own site, 15 are
third-party aggregators or blogs, and 2 are another institution relaying a scholarship. Aggregator listing pages
were stored as single records and cause most conflicts (several programmes' dates on one page). Errors seen:
a page-wide latest date taken as the deadline (Indian NSP: student closing 31-10-2026 vs 30/11 for officials),
host country read as eligibility (Eiffel "include FR"), a .edu.vn school blog counted as official.

### Controlled live run, 2026-10-17 08:21-09:02 UTC (scratch data, final code, no web search)

Search provider: none configured (`search-check` reports it). Sources: 30 registry sources (27 countries and 2
international organisations), plus the DAAD, Erasmus Mundus and EURAXESS adapters.

| Stage | Result |
|---|---|
| Pages retrieved / failed / skipped as not opportunities | 506 / 7 / 50 (30 irrelevant, 10 guidance, 6 listings, 4 news) |
| Sitemap URLs seen / programme section pages read | 336 / 25 |
| Unique records / duplicates merged | 415 (DAAD 148, Erasmus Mundus 217, registry pages 50) / 41 |
| EURAXESS | 0 records (offers robots-disallowed), 6 funding-scheme leads |
| Records re-checked against an official source | 371 of 415 (44 official pages unreachable or robots-blocked) |
| Record status after verification | 283 officially confirmed (at least one key field), 80 official page states no key field, 44 source unavailable, 8 conflicting |
| Field level: confirmed current deadline / nationality / funding / all three | 68 / 194 / 247 / 25 |
| Missing: current dated deadline / nationality / funding amount / language test | 84% / 53% / 78% / 97% |
| Runtime | 16 min discovery + 25 min verification |

The 8 conflicts are real: two NRF calls for different years merged into one record (dedup across cycles), a
TWAS listing whose dates belong to different calls, two application URLs on one CSC page, and differing
eligible-country statements on two Manaaki pages.

## Known limitations

- Independent accuracy (set B, 13 pages): deadlines 3/5, nationality 3/8, amounts 2/3, ages 3/6; about one in
  three extracted values unsupported. The tuned set-A scores do not transfer - more held-out data is needed.
- Live search has run on 10 of 231 countries only (40 queries). Lead precision is low: about a third of new
  records are aggregator pages, and listing pages are not yet split into programmes. "Confirmed" means the
  official page states the value; it does not prove the right value was picked from that page.
- About 13 of 92 sources refuse automated clients; EURAXESS offers are robots-disallowed; some sites rate-limit (429).
- Two-digit years, deadlines without any year, per-level age tables and heading-introduced country lists are the
  main extraction misses; PDFs with embedded CID fonts without ToUnicode maps stay unreadable without pypdf.
- Erasmus Mundus scholarship terms live on ~200 different consortium sites with no common format.

## Remaining work (by importance)

1. Label a set C of live official pages (deadline kind, scope, cycle) to measure deadline accuracy
   independently; then run `strategy-run` region by region.
2. Grow held-out set B to 50+ pages across more languages before further rule tuning; add a set C.
3. Fix the B-set error classes: heading-introduced country lists, per-level age tables, two-digit years, host
   country mistaken for nationality.
4. Per-consortium parsing (or AI with quotes) for Erasmus Mundus scholarship terms.
5. Optional pypdf for difficult PDFs; a larger local model if hardware allows.
6. HTTP layer over `ScholarshipService` and a multi-tenant store when the website phase starts.
