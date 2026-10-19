# /scholar-setup - Applicant Profile for the Scholarship Agent

Create or update the applicant profile the scholarship agent evaluates against.

**Prerequisites:** none. **Writes:** `data/private/private.db` (gitignored, 0600). **Output:** JSON with `profile` and `missing`.

## Steps

1. Show the current profile if one exists: `python3 -m scholarship_agent profile`. An `error` saying no profile means start fresh.
2. Collect, conversationally and only what the user is willing to share: citizenship(s), country of residence, date of birth (only needed for age-limited awards - say so), education (degree, field, institution, country, dates, GPA **and** its scale, language of instruction), target level and intake, preferred destinations, disciplines, research interests, language tests (test, score, date), work/research experience with dates, projects, publications, awards, funding need (`full` | `tuition` | `partial` | `any`), and which documents they already hold (passport, transcripts, ...).
   - If the user has CVs or transcripts in `documents/`, read them and propose values - but mark anything you derived rather than were told as **inferred**: put it under `inferred` (e.g. `{"inferred": {"gpa": {"value": 3.4, "confirmed": false, "source": "document:transcript.pdf"}}}`) until the user confirms it. Inferred facts are never used as proof of eligibility.
3. Write the JSON to a temporary file outside the repo and apply it: `python3 -m scholarship_agent setup --file <tmp.json>` (fields merge into the stored profile; a list you pass replaces the stored list). Single fields: `--set target_intake='"2027-09"'`. Delete the temp file afterwards.
4. Report what was saved and every item in `missing`, with why it matters (e.g. no GPA → GPA requirements stay "unknown").

## Rules
- Countries may be names or ISO codes; unknown names are rejected - ask, don't guess.
- Never invent grades, scores, dates or experiences.
- Updating the profile never touches saved applications or documents.
- Privacy: `python3 -m scholarship_agent export-data` gives the user a full copy; `delete-data --yes` removes all private data (ask first - it cannot be undone).
