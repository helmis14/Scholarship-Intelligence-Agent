# /cv - Tailored Academic CV

**Input:** `<opportunity>`. **Output:** JSON with the CV (Markdown) and its review.

## Steps
1. `python3 -m scholarship_agent cv "<opportunity>"` builds the CV from confirmed profile facts only and stores it as a new version.
2. Tailor ordering and emphasis for the opportunity's selection criteria if useful, without adding facts, then `save-draft "<opportunity>" scholarship_cv --file <tmp.md>`.
3. Export: `python3 -m scholarship_agent export "<opportunity>" scholarship_cv --format docx`.
