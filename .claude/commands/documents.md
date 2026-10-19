# /documents - Document Readiness Audit

**Input:** `<opportunity>`. **Output:** JSON `matrix`, `drafts` (kind, version, review_passed), `missing`, `notes`.

## Steps
1. `python3 -m scholarship_agent documents "<opportunity>"`.
2. Report what is held, drafted (and whether the latest draft passed review), and missing - mandatory first - with the next action and start-by date for each.
