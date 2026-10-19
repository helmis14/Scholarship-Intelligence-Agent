# /review - Pre-Submission Audit

**Input:** `<opportunity>`. **Output:** JSON `ready`, `blockers`, `next_deadline`, `eligibility`.

## Steps
1. `python3 -m scholarship_agent review "<opportunity>"`.
2. If not ready, list each blocker with the command that resolves it (`/verify`, `/match`, `/documents`, `/essay`). If ready, give the deadline (with time zone) and remind the user to submit on the official portal and then `/track <opportunity> --status submitted`.
