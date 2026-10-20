# Privacy review and terms checklist

This is an engineering review of what the code stores, sends and exposes, and a checklist of what a public service must add. **It is not legal advice.** Before a public launch, have a lawyer check the terms and privacy notice against the laws of the countries where users live (for example GDPR in the EU/UK and the personal data protection law of Indonesia).

## 1. What is stored, where

| Data | File | Contains personal data | Shared |
|---|---|---|---|
| Scholarship records, deadlines, verifications, page cache, search jobs, issue reports | `catalog.db` | No (issue reports hold no profile id and no contact detail; e-mail addresses and phone numbers are removed from the note) | Could seed a website |
| Applicant profile (name, citizenship, education, tests, experience, achievements), applications, checklists, documents and versions, reminders, outcomes | `private/private.db` (mode 0600, directory 0700) | **Yes** | Never |
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

## 4. Gaps before a multi-user public service

1. **Authentication and tenant isolation.** One data directory per tenant exists in the service constructor, but there is no login, session, or per-user authorisation layer. Add one before exposing any route that takes a `profile_id`.
2. **Encryption at rest and backups.** SQLite files are permission-protected only. A hosted service needs disk encryption, encrypted backups, and a backup retention that honours deletion (a deleted profile must age out of backups).
3. **Rate limiting and abuse controls** on `report_issue`, search and ingest routes; CAPTCHA on public forms.
4. **Retention.** Define how long `profile_history` and `document_versions` are kept; offer "delete my account" in one step.
5. **Sensitive data minimisation.** The profile can hold family and financial circumstances written into essays. Mark these fields as sensitive, exclude them from logs and from model prompts unless the user opts in per document.
6. **Children.** Many programmes target students under 18. Decide the minimum age, parental-consent flow, and whether to accept minors' data at all.
7. **Cross-border transfer.** If users are in the EU/UK or Indonesia and servers elsewhere, document the transfer basis.
8. **Audit log** of operator access to private data (none exists; today there is no operator access path by design).

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

- [ ] Lawyer review of terms and privacy notice for target countries.
- [ ] Authentication, authorisation, and per-tenant isolation tested.
- [ ] Encryption at rest and tested restore plus deletion-from-backup procedure.
- [ ] Rate limits and abuse controls on public routes.
- [ ] Data-processing agreement with the model provider, or documents drafted only on the user's side.
- [ ] Contact address set in `SCHOLAR_USER_AGENT`; takedown address published.
- [ ] Fresh-set accuracy check passed (wrong claims under 5% of decisions with `SCHOLAR_RISK_GATE=strict`, quotation on every shown value, two labellers agree).
- [ ] "Report a mistake" visible next to every value, operator process to resolve within a stated time.
