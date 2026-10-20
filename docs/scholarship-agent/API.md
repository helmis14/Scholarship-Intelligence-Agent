# Service boundary (`scholarship_agent.service.ScholarshipService`)

The CLI and the Claude Code commands are thin callers of this class. A future
web backend should call the same methods; each takes plain arguments and
returns a JSON-serialisable dict with `schema_version` (currently `"1.0"`).
Domain logic lives in the modules below it; nothing in the service prints,
prompts, sends email or submits anything.

```python
from scholarship_agent.service import ScholarshipService
from scholarship_agent.store import Store

svc = ScholarshipService(store=Store("/srv/tenants/42"))   # one data dir per tenant
svc.setup_profile({"citizenships": ["ID"], "target_levels": ["master"]}, profile_id="user-42")
svc.discover(destinations=["DE"], levels=["master"], use_search=True)
svc.rank(profile_id="user-42")
```

Constructor: `store`, `fetcher` (`net.Fetcher`, injectable transport), `search`
(a `SearchProvider`, `None` for registry-only, default: from env), `today`
(fixed date for tests/replays), `sources` (registry list), `llm` (an
`LLMProvider` with `complete(brief) -> str`).

Errors: `service.NotFound` (unknown opportunity/profile, maps to HTTP 404),
`tracker.TransitionError` and `ValueError` (invalid input or state, HTTP 400/409).

| Method | Suggested route | Returns (top-level keys) |
|---|---|---|
| `setup_profile(patch, profile_id)` | `PATCH /profiles/{id}` | `profile`, `missing` |
| `get_profile(profile_id)` | `GET /profiles/{id}` | `profile`, `missing` |
| `export_private_data(profile_id)` | `GET /profiles/{id}/export` | `profile`, `applications`, `status_history`, `checklist`, `documents`, `outcomes` |
| `delete_private_data(profile_id)` | `DELETE /profiles/{id}` | `deleted` (row counts) |
| `report_issue(ref, field, note, shown_value)` | `POST /opportunities/{id}/reports` | `report_id`, `status`; stores no profile or contact detail; two open reports on a field hold it as `needs_review` |
| `list_issue_reports(status, ref)` / `resolve_issue_report(id, status, resolution)` | operator routes | `reports`, `count` / `status` |
| `discover(destinations, levels, disciplines, nationality, source_ids, use_search)` | `POST /discovery-jobs` | `job_id`, `pages_fetched`, `opportunities_new`, `opportunities_updated`, `duplicates_merged`, `failures`, `injection_flags`, `search_provider`, `queries`, `sources_used` |
| `scrape(urls, provider, countries)` | `POST /ingest` | same as discover |
| `verify(ref, official_url)` | `POST /opportunities/{id}/verify` | `status`, `confirmed`, `conflicting`, `unverified`, `historical_deadlines`, `conflicts`, `notes` |
| `refresh(max_age_days, limit)` | scheduled job | `refreshed`, `results` |
| `get_opportunity(ref)` | `GET /opportunities/{id}` | `opportunity`, `deadline_history`, `verifications` |
| `search_opportunities(country, level, text, status)` | `GET /opportunities` | `results`, `count` |
| `sources_status(check)` | `GET /sources` | `sources`, `checks`, `coverage`, `search_provider`, `recent_jobs` |
| `add_source(entry)` | `POST /sources` | `added`, `file` |
| `match(ref, profile_id)` | `GET /profiles/{id}/matches/{opp}` | `eligibility`, `funding`, `verification_status`, `last_verified_at` |
| `funding_estimate(ref, tuition_per_year, living_per_month, currency, fx)` | `GET /opportunities/{id}/funding` | `classification`, `estimate` |
| `rank(profile_id, weights, top, include_expired)` | `GET /profiles/{id}/ranking` | `ranked`, `excluded`, `weights`, `disclaimer`, `as_of` |
| `plan(ref, profile_id)` | `POST /applications/{opp}/plan` | `application_id`, `matrix`, `timeline`, `notes` |
| `prepare(ref, kinds, profile_id, save)` | `POST /applications/{opp}/documents` | `application_id`, `writing_tasks`, `documents` |
| `brief(ref, kind, profile_id)` | `GET /applications/{opp}/briefs/{kind}` | `brief` |
| `save_draft(ref, kind, content, profile_id)` | `PUT /applications/{opp}/documents/{kind}` | `saved`, `review` |
| `review_draft(ref, kind, content, profile_id)` | `POST /reviews` | `review` |
| `documents_audit(ref, profile_id)` | `GET /applications/{opp}/readiness` | `matrix`, `drafts`, `missing`, `notes` |
| `pre_submission_review(ref, profile_id)` | `GET /applications/{opp}/pre-submission` | `ready`, `blockers`, `next_deadline`, `eligibility` |
| `export_document(ref, kind, fmt, out_dir, profile_id)` | `GET /applications/{opp}/documents/{kind}.docx` | `file` |
| `track(ref, status, note, item, item_status, profile_id)` | `GET/PATCH /applications[/{opp}]` | `applications` or `application`, `checklist` |
| `deadlines(within_days, profile_id, tracked_only)` | `GET /profiles/{id}/deadlines` | `confirmed`, `expected_unconfirmed`, `unknown`, `historical_recent`, `urgent_tasks` |
| `reminders(profile_id, notifier)` | scheduled job | `reminders`, `delivery` |
| `outcome(ref, result, lessons, profile_id)` | `POST /applications/{opp}/outcome` | `application` |
| `report(profile_id)` | `GET /profiles/{id}/report` | counts, top ranked, deadlines, coverage, jobs, lessons |

`ref` accepts an opportunity id, an id prefix, or a unique title fragment.
Object shapes are the `to_dict()` forms of the dataclasses in
`scholarship_agent/models.py`.

## Extension points

- **Search provider:** implement `search.SearchProvider` (`name`, `available()`, `search(query, limit, lang)`).
- **Sources:** add entries to `data/sources.local.json` or call `add_source`.
- **Notifications:** implement `tracker.Notifier.deliver(reminders)`; an email or calendar adapter must require the user's explicit approval before sending.
- **Drafting model:** implement `documents.LLMProvider.complete(brief)`; output always goes through `review.review`.
- **Storage:** `store.Store` is the only module that touches SQL; a server database can replace it behind the same methods.
