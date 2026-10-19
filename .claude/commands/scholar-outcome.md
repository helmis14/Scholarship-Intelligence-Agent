# /scholar-outcome - Record a Scholarship Result

**Input:** `<opportunity> accepted|rejected|withdrawn|expired|interview|waitlisted [--lessons "..."]`.

## Steps
1. Ask what happened and what the user learned (feedback, interview questions, what they would change).
2. `python3 -m scholarship_agent outcome "<opportunity>" <result> --lessons "<text>"`.
3. Lessons appear in `/report` and should inform the next essays for similar opportunities.
