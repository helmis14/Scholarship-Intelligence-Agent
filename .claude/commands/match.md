# /match - Explain Eligibility and Fit

**Input:** `<opportunity>`. **Prerequisites:** profile. **Output:** JSON `eligibility` (`decision` ∈ ELIGIBLE, LIKELY_ELIGIBLE, UNCERTAIN, INELIGIBLE, INSUFFICIENT_INFORMATION; `track`; `supporting_requirements`; `applicant_facts_used`; `matches`; `mismatches` with `hard`/soft; `missing_information`; `uncertainties`; `next_action`; `checks`) plus `funding`.

## Steps
1. `python3 -m scholarship_agent match "<opportunity>"`.
2. Present, in this order: decision; the official requirements it rests on (with source URL and verification status); applicant facts used; confirmed matches; disqualifying mismatches (mandatory vs preference); missing information; uncertainties; the recommended next action.
3. For funding, give the class and its reasons. For a cost estimate: `python3 -m scholarship_agent funding "<opportunity>" --tuition 18000 --living 1100 --currency EUR` (pass `--fx '{"EUR->USD":1.08}'` only with a rate the user accepts; the agent never fetches rates silently).

## Rules
- A mismatch backed by unverified evidence makes the decision UNCERTAIN, never INELIGIBLE.
- Never call an English test waived because a page does not mention it; an MOI route counts only where the source documents it.
