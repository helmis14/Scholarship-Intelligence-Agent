# /deadlines - Upcoming Deadlines and Urgent Actions

**Input:** optional `--days N` (default 90), `--tracked` for tracked applications only. **Output:** JSON `confirmed` (with days_left, time, timezone, source), `expected_unconfirmed` (wording only, no invented dates), `unknown`, `historical_recent`, `urgent_tasks`.

## Steps
1. `python3 -m scholarship_agent deadlines --days 90`.
2. Present confirmed deadlines chronologically, then expected-but-unconfirmed ones with their wording ("usually early February"), then urgent checklist tasks.
3. Reminders: `python3 -m scholarship_agent reminders` (console) or `--ics data/private/reminders.ics` to produce a calendar file the user can import. Nothing is emailed or sent.

## Rules
- Never turn a historical or approximate date into a precise one.
