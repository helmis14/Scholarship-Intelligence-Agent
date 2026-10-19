# /track - Review and Update Application Status

**Input:** none (list all) or `<opportunity> [--status <status>] [--note "..."] [--item "<checklist item>" --item-status done]`.
Statuses: discovered, awaiting_verification, eligibility_review, shortlisted, preparing_documents, waiting_for_recommendations, ready_for_review, submitted, assessment_or_interview, awaiting_decision, accepted, rejected, withdrawn, expired.

## Steps
1. `python3 -m scholarship_agent track` lists applications; with an opportunity it shows status history and checklist.
2. Apply changes the user states. Invalid transitions (e.g. discovered → accepted, anything after a final state) are refused with the allowed next states - relay them.
3. Only mark `submitted` when the user says they submitted it themselves. The agent never submits applications or sends messages.
