# /plan - Application Plan and Requirements Checklist

**Input:** `<opportunity>`. **Prerequisites:** profile. **Writes:** application record + checklist. **Output:** JSON `matrix` (requirement, category admission/scholarship/visa/enrollment, mandatory/optional/unclear, source, readiness, format, translation, certification, prep_days, deadline + certainty, start_by, dependencies, missing_information, next_action, status, urgent), `timeline` (dependency-ordered), `notes`.

## Steps
1. `python3 -m scholarship_agent plan "<opportunity>"`.
2. Present the matrix grouped by category, urgent items first, then the timeline. Read out `notes` - especially "No visa requirements found in the evidence (not the same as none existing)".
3. Mark progress later with `python3 -m scholarship_agent track "<opportunity>" --item "CV" --item-status done`. Re-running `/plan` keeps items already marked done.

## Rules
- Only requirements in the evidence (or directly implied, like a test certificate for a stated IELTS minimum) are listed. Do not add "usual" documents; if the source lists none, say the checklist is incomplete and point to the application form.
