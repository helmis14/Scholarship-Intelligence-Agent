# Privacy review and terms checklist

This is an engineering review of what the code stores, sends and exposes, and a checklist of what a public service must add. **It is not legal advice.** Before a public launch, have a lawyer check the terms and privacy notice against the laws of the countries where users live (for example GDPR in the EU/UK and the personal data protection law of Indonesia).

## 1. What is stored, where

| Data | File | Contains personal data | Shared |
|---|---|---|---|
| Scholarship records, deadlines, verifications, page cache, search jobs, issue reports | `catalog.db` | No (issue reports hold no profile id and no contact detail; e-mail addresses and phone numbers are removed from the note) | Could seed a website |
| Applicant profile (name, optional phone number and LinkedIn address, citizenship, education, tests, experience, achievements), applications, checklists, documents and versions, reminders, outcomes | `private/private.db` (mode 0600, directory 0700) | **Yes** | Never |
| Model usage ledger (`llm_usage`) and response cache (`llm_cache`) | `catalog.db` | No: counts, latency and estimated cost only; cached responses are answers about public pages | No |
| API keys | environment or a file outside the repository (`~/.config/...`) | Secret | Never committed; `.env.example` has empty values |

Keys are never written to logs, the ledger or error messages (`anthropic_llm.py`, `cloud_llm.py`). The repository's `.gitignore` excludes `data/` and `.env*`.

## 2. What leaves the machine

1. **Requests to scholarship sites**, with a fixed User-Agent (`SCHOLAR_USER_AGENT`, default names the agent; set a contact address for a public deployment). robots.txt is read and obeyed; a site that blocks automated clients is skipped.
2. **Search queries** to the configured provider (default: a local SearXNG; a hosted provider sees the query text only).
3. **Page text to a model**, only if `AI_PROVIDER` is set and paid calls are explicitly allowed. The extraction calls send the *page text*, never the applicant profile.
4. **Applicant facts to a model**, only when a model is used to draft documents (`documents.brief` carries a fact pack of confirmed profile facts). In the Claude Code workflow this is the user's own session. For a hosted service this is the one flow that needs explicit, per-use consent and a data-processing agreement with the model provider.
5. Nothing is sent to analytics. Nothing is e-mailed or submitted for the user: the agent never submits an application or sends a message.

## 3. User rights (already implemented)

- **Access/portability:** `export-data` / `export_private_data` returns the profile, applications, status history, checklist, documents and outcomes.
- **Erasure:** `delete-data --yes` / `delete_private_data` removes them and returns row counts.
- **Correction of public data:** `report-issue` / `report_issue` (this round). Two open reports on one field hold that field as `needs_review` until an operator resolves them; `issues` lists and resolves reports.
- **Transparency:** every claimed value carries its quotation and the page URL; low-precision claim kinds are shown as unverified (`SCHOLAR_RISK_GATE`).

## 4. Multi-user service: done in round 46, and what is left

Done (code and tests in `accounts.py`, `crypto.py`, `web.py`, `tests/test_scholarship_round46.py`):

1. **Authentication and tenant isolation.** Accounts with scrypt password hashes, expiring sessions (30 days, 7 idle
   days), lockout after 5 failed logins, password change and reset (reset needs an SMTP server; nothing is sent without
   one). The HTTP API (`serve`) maps every private route to the logged-in account's own profile; tested.
2. **Encryption at rest.** Private free text and the e-mail address are AES-256-GCM encrypted per field; production mode
   requires keys from the environment; `encrypt-private` encrypts older rows and rewraps after key rotation;
   `security-status` reports the state without showing secrets.
3. **Rate limits** on login, registration, reset and "report a mistake"; 1 MB body limit; generic errors.
4. **Retention.** Earlier profile versions: last 20 (`SCHOLAR_PROFILE_HISTORY_KEEP`). Account deletion removes the account,
   sessions, events and all private records in one step (`DELETE /api/v1/account`).
5. **Consent records.** Registration requires accepting the current terms and privacy versions and confirming age; the
   AI-drafting choice is stored and can be changed.
6. **Account event log** without IP address or user agent; the per-user lessons list no longer shows other users'
   outcomes.

Left before launch: lawyer review (packet and drafts in `legal/`), disk and backup encryption at the host and a backup
period that honours deletion, CAPTCHA or e-mail confirmation on registration, a decision on minors, transfer basis for
the hosting, e-mail and AI providers, monitoring and a penetration test.

## 5. Terms of service: points to include

1. **Not an official source.** The service reports what official pages say, with quotations; the user must confirm on the official page before applying. No guarantee of accuracy, completeness or availability; the published accuracy figures describe test sets, not every record.
2. **No affiliation** with any scholarship provider; names and marks belong to their owners.
3. **No application submission.** The service never applies, pays or signs on the user's behalf.
4. **AI-assisted documents.** Drafts are the user's responsibility; follow each provider's rules on AI assistance; the service refuses to invent facts and flags unsupported claims, but cannot guarantee that a draft is acceptable.
5. **Sources and takedown.** Content is gathered from public pages with robots.txt respected; a provider can ask for removal of its record; a contact address for requests.
6. **User content.** The user owns their profile and documents, can export and delete them; the service uses them only to provide the service.
7. **Acceptable use.** No scraping of the service, no false reports (reports are reviewed and may be rejected), no use for fraud.
8. **Liability limit and governing law** — to be written by a lawyer.
9. **Changes and contact.**

## 6. Privacy notice: points to include

What is collected (section 1), why (to match and draft), the legal basis (consent/contract), who receives it (model provider only with consent, hosting provider), retention, user rights and how to exercise them (section 3), security measures, children's policy, and a contact for requests and complaints.

## 7. Pre-launch checklist

- [ ] Lawyer review of terms and privacy notice for target countries (packet and drafts: `legal/`).
- [x] Authentication, authorisation, and per-tenant isolation tested (round 46).
- [x] Encryption at rest (round 46).
- [ ] Tested restore plus deletion-from-backup procedure at the host.
- [x] Rate limits on public routes (round 46).
- [ ] CAPTCHA or e-mail confirmation on registration.
- [ ] Data-processing agreement with the model provider, or documents drafted only on the user's side.
- [ ] Contact address set in `SCHOLAR_USER_AGENT`; takedown address published.
- [x] Fresh-set accuracy check passed: set X 2.1% wrong claims with the strict gate and the second reading (round 45).
- [ ] Two labellers agree.
- [ ] "Report a mistake" visible next to every value, operator process to resolve within a stated time.
