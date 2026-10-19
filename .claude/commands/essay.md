# /essay - Tailored Scholarship Essay

**Input:** `<opportunity>` and optionally `--kind essay|personal_statement|motivation_letter|sop|leadership_essay|career_goals` (default `essay`). **Output:** JSON with the brief, skeleton and review.

## Steps
1. `python3 -m scholarship_agent brief "<opportunity>" <kind>` - read the prompt, limit, selection criteria and fact pack. If `prompt` is empty, say the exact question was not found and ask the user to paste it from the application form.
2. Ask the user for the personal material the prompt needs that `FACT_PACK` lacks (motivations, a specific moment, plans). Do not fill these gaps yourself.
3. Draft to `brief.standard` (structure in order, the do/avoid lists; a specific opening, one idea per paragraph, every criterion with an example, a concrete plan at the end), then review and store: `python3 -m scholarship_agent save-draft "<opportunity>" <kind> --file <tmp.md>`.
4. Iterate until review has no errors; present the final text with the word count and the review checklist (limit, required topics, unsupported claims, consistency with the CV, placeholders).
