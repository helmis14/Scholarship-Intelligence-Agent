# /verify - Verify an Opportunity Against Its Official Source

**Input:** `<opportunity>` (id, id prefix, or a unique title fragment) and optionally `--official-url <url>`.
**Network:** yes. **Output:** JSON with `status`, `confirmed`, `conflicting`, `unverified`, `historical_deadlines`, `conflicts`, `notes`.

## Steps
1. `python3 -m scholarship_agent verify "<opportunity>" [--official-url <url>]`.
2. Present per field: confirmed (with source URL), conflicting (show both values and both sources - never pick one silently), unverified, and deadlines that turned historical.
3. If the result says no official source is known, find the provider's own page (WebSearch, then confirm the domain belongs to the provider) and re-run with `--official-url`. Never treat an aggregator as official.
4. Language tests: if no test is stated, say so and check the **university's admission rules** separately - a scholarship page's silence is not a waiver.

## Rules
- Official sources are the authority for eligibility, funding, deadlines and instructions.
- `python3 -m scholarship_agent refresh --max-age-days 14` re-verifies everything stale; it is the job to schedule for deadline refresh.
