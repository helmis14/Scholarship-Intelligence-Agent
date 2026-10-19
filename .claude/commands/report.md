# /report - Scholarship Status Report

**Output:** JSON with opportunity counts by verification status, eligibility distribution for the profile, top ranked, applications by status, shortlisted, upcoming and expected deadlines, urgent tasks, source coverage, recent discovery jobs, lessons.

## Steps
1. `python3 -m scholarship_agent report`.
2. Summarise in this order: action needed this week (urgent tasks, deadlines ≤ 30 days), active applications, shortlist, discovered-but-unverified count, coverage (countries with an official source vs total), and recent discovery failures.
3. If the user wants a file, write the Markdown summary under `data/private/` (gitignored), not in a tracked folder.
