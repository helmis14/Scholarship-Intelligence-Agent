# Legal review packet (for counsel)

Prepared by the engineering side on 2026-10-23 for a lawyer who reviews the service before a public launch. It describes
what the software does and lists the decisions only counsel can take. **It is not legal advice and makes no legal
conclusion.** Section 9 lists the questions to answer; the draft privacy notice and terms in this folder are starting
points for counsel to rewrite.

Laws we expect to be relevant (counsel to confirm the list): Indonesia's Personal Data Protection Law (UU No. 27 Tahun
2022, "UU PDP") and its implementing rules; the EU GDPR and the UK GDPR if people in Europe can sign up; local rules where
other users live; copyright and database rights for content quoted from scholarship web pages; consumer-protection rules for
the terms of service; Indonesia's language law for agreements with Indonesian users (UU No. 24 Tahun 2009).

## 1. What the service does

A person searches a catalogue of scholarships built from public pages of universities, governments and foundations. Each
shown value (who may apply, funding, deadline, whether the call is open) carries a short quotation and a link to the
official page. With an account, the person stores an applicant profile, sees which programmes fit, tracks applications and
deadlines, and keeps drafts of application documents. The service never applies, pays or sends anything on the person's
behalf.

## 2. Records of processing

| Data | Whose | Purpose | Proposed legal basis (counsel to decide) | Where | Retention (current code) |
|---|---|---|---|---|---|
| E-mail address | account holder | login, password reset, service notices | contract | `private.db` `users.email`, AES-256-GCM encrypted; found by keyed hash | until account deletion |
| Password | account holder | login | contract | scrypt hash only | until account deletion |
| Session tokens | account holder | keep a person logged in | contract | SHA-256 hash only | 30 days, or 7 idle days |
| Account events (register, login, failed login, password change, export) | account holder | security, abuse prevention | legitimate interest / legal obligation | `auth_events`, no IP address, no user agent | until account deletion (counsel: set a shorter period?) |
| Consent record (terms and privacy versions, AI-drafting choice, age confirmation, time) | account holder | proof of consent | legal obligation | `users.consent` | until account deletion |
| Applicant profile: name, phone number (asked at sign-up), citizenships, residence, education, grades, tests, experience, achievements, languages, preferences; may include financial or family circumstances the person writes | account holder | matching, eligibility checks, application planning | contract; explicit consent for specific data (see §5) | `profiles`, encrypted | until deleted; earlier versions: last 20 (`SCHOLAR_PROFILE_HISTORY_KEEP`) |
| Applications, status history and notes, checklists | account holder | tracking | contract | encrypted where free text | until deleted |
| Document drafts and their review notes | account holder | drafting help | contract | `document_versions`, encrypted | until deleted |
| Outcomes and lessons | account holder | the person's own record | contract | encrypted | until deleted |
| Reminders (scholarship title, deadline) | account holder | reminders | contract | plain text (public facts only) | until deleted |
| "Report a mistake" notes | anyone | correct public data | legitimate interest | `catalog.db`, no account link; e-mail addresses and phone numbers removed from the text | until resolved (counsel: set a period) |
| Scholarship pages, quotations, deadlines | providers' public pages | the catalogue | legitimate interest (public information) | `catalog.db` | refreshed; old deadlines kept as history |
| Server logs | anyone | operation | legitimate interest | stderr: method, path without query, status; no token, body or IP is written by the app (the reverse proxy logs IPs: set its retention) | proxy setting |

## 3. Rights of the person and how the software meets them

| Right (UU PDP / GDPR) | Implemented as |
|---|---|
| Information | privacy notice (draft in this folder), shown at registration; the API refuses registration without accepting the current versions |
| Access and a copy; portability | `GET /api/v1/account/export` (JSON with account, consent, events, profile, applications, documents, outcomes) |
| Correction | `PATCH /api/v1/profile`; public data: "report a mistake" |
| Deletion | `DELETE /api/v1/account` (password required) deletes the account, sessions, events and every private record in one step and compacts the database file |
| Withdraw consent | `PATCH /api/v1/account/consent` (AI drafting); full withdrawal = account deletion |
| Object to automated decisions | the service only ranks and explains; it decides nothing for the person (counsel: confirm this is not automated decision-making with legal effect) |
| Response time | UU PDP sets short deadlines for several requests (counsel: confirm, e.g. 3 x 24 hours); the self-service routes answer at once |

Backups: a deleted account remains in backups until they expire. Counsel to approve the backup period and wording (see §7).

## 4. Security measures (UU PDP security obligations; GDPR Art. 32)

- Encryption at rest of every private free-text field and the e-mail address: AES-256-GCM with per-field binding
  (`scholarship_agent/crypto.py`); keys from the environment or a secret store in production (`SCHOLAR_ENV=production`
  refuses to start without them); key rotation with `SCHOLAR_DATA_KEYS` and `encrypt-private`.
- Database files `0600` in a `0700` directory; the public catalogue and private data are separate files.
- Passwords: scrypt (N=2^15), 10 to 256 characters, common passwords refused; lockout after 5 failed logins for 15
  minutes; per-client rate limits on login, registration and reset; no hint whether an address is registered at login or
  reset (registration of an existing address is refused, which reveals that it exists: counsel and product to decide if
  e-mail confirmation should replace this).
- Sessions: random 256-bit tokens stored as hashes, 30-day lifetime, 7-day idle timeout, all ended on password change.
- HTTP: runs behind an HTTPS reverse proxy (binds to localhost by default); HSTS, no-store caching, strict content
  security policy, CORS only for listed front ends, 1 MB body limit, generic error messages.
- Isolation: every private route uses the profile of the logged-in account only; tested (`tests/test_scholarship_round46.py`).
- Data sent to an AI model: the web API sends no personal data to any model. Command-line drafting can send a fact pack
  of the applicant's own confirmed facts to the configured model; a hosted version must ask for the AI-drafting consent
  (recorded in `users.consent`) before any such call.

Not yet done (operator tasks): disk and backup encryption at the hosting provider, backup retention and restore tests, a
penetration test, monitoring and alerting, a named person responsible for data protection.

## 5. Specific (sensitive) data and children

- UU PDP treats some data as specific personal data (for example health, children's data, personal financial data). Profiles
  and essays can contain financial hardship, health or family circumstances written by the person. Counsel: is explicit
  consent at registration enough, or is a separate consent needed when such text is saved? Should the product discourage
  entering health data?
- Children: many scholarships are for secondary-school students. The current registration requires confirming age 18 or
  more (or a parent's or guardian's consent where the law requires it). Counsel: set the minimum age per country (GDPR
  allows 13 to 16 for consent to online services; UU PDP requires a parent's or guardian's consent for children's data)
  and decide whether to build a parental-consent flow or refuse minors.

## 6. Processors and transfers

| Recipient | What | Where | Status |
|---|---|---|---|
| Hosting provider (to be chosen) | everything stored | to be chosen | needs a data processing agreement |
| E-mail provider (SMTP, only if password reset is switched on) | e-mail address, reset code | to be chosen | needs a data processing agreement |
| Anthropic (Claude API) | public scholarship page text for the second reading; personal data only if AI drafting is enabled with consent | United States | check Anthropic's commercial terms and data processing addendum for the planned use |
| Search engines (via a self-hosted SearXNG) | search queries about scholarships, no personal data | various | none |

Counsel: the basis for transfers out of Indonesia (UU PDP requires an equal or higher level of protection, adequate and
binding safeguards, or the person's consent) and out of the EU/UK if those users are accepted.

## 7. Breach response (draft procedure)

1. Contain: revoke sessions (`DELETE FROM auth_tokens`), rotate keys (`SCHOLAR_DATA_KEYS` + `encrypt-private`), close the
   entry point.
2. Assess within hours: what data, whose, encrypted or not, keys exposed or not.
3. Notify: UU PDP requires written notice to the persons and the supervisory institution within 3 x 24 hours of a failure
   of protection (counsel to confirm the details and the institution); GDPR requires notice to the authority within 72 hours
   where it applies. Keep a record of every incident.
4. Fix and review; tell users what changed.

## 8. Public-content questions

- The catalogue quotes short passages from official pages with links, respects robots.txt and skips sites that refuse
  automated clients. Providers can ask for removal ("report a mistake" or a published contact address).
- Counsel: is quoting these passages fine under Indonesian copyright law and in other target countries? Does the EU
  database right matter for collections of pages from EU universities? Which wording should the takedown policy use?
- Names and logos of providers are not used as branding; the site must not suggest an affiliation.

## 9. Questions for counsel

1. Which laws apply, given where the operator is established and where users live? Is an EU representative needed if EU
   users can register?
2. Legal basis for each row in §2; is consent the right basis for specific data in profiles and essays?
3. Minimum age and parental-consent requirements per target country.
4. Is a data protection officer required (UU PDP Art. 53), and is a data protection impact assessment required before
   launch (UU PDP Art. 34; GDPR Art. 35)? A draft can be written from §2 to §6.
5. Transfer basis for the hosting provider, the e-mail provider and Anthropic.
6. Retention periods for account events, reports and backups.
7. Terms: limitation of liability, disclaimer that the service is not an official source, governing law and dispute
   forum, language versions, consumer-protection limits.
8. Copyright and database-right position of the quotations; takedown wording.
9. Whether showing a ranking and an eligibility explanation counts as profiling or automated decision-making that needs
   extra notice or an opt-out.

## Changes on 2026-10-28 (before going public)

- Log-in runs through Supabase (e-mail and password are held by Supabase; this server sees only a verified session). A
  CAPTCHA (Cloudflare Turnstile, through Supabase's bot protection) can be turned on for sign-up, log-in and password
  reset; Cloudflare then receives technical browser signals. Both are processors to list in the notice and in the
  records of processing.
- A phone number is asked at sign-up and kept, encrypted, in the profile; it appears on the CV the person downloads.
- Backups: one archive every night (catalogue, private database, keys), 14 kept; restore keeps the data it replaces as a
  "pre-restore" archive. Deleted accounts therefore disappear from backups within 14 days.
- Public programme pages (/p/<id>) and a sitemap carry catalogue data only, never personal data.
- The operator's name, address and e-mail addresses are filled into the notice and the terms from the server's
  settings (SCHOLAR_OPERATOR_NAME, SCHOLAR_OPERATOR_ADDRESS, SCHOLAR_CONTACT_EMAIL, SCHOLAR_PRIVACY_EMAIL,
  SCHOLAR_TAKEDOWN_EMAIL). Counsel still writes liability, governing law, legal bases, transfers and response times.

