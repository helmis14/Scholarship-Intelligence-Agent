# /scholar-rank - Rank Scholarships for the Applicant

Rank stored opportunities against the profile with transparent, weighted components.

**Prerequisites:** a profile (`/scholar-setup`) and opportunities (`/discover`). **Output:** JSON with `ranked` (score, eligibility, funding, next deadline, per-component value/weight/contribution/reason), `excluded` (hard failures, expired cycles), `weights`, `disclaimer`.

## Steps
1. `python3 -m scholarship_agent rank --top 15` (custom weights: `--weights '{"funding":0.3,"deadline":0.15}'`; persistent weights: `data/ranking_weights.json`).
2. Present a table: rank, title, score, eligibility, funding class, next deadline (with certainty). Below it, the two biggest positive and negative components for the top 5.
3. List `excluded` separately with the reason - hard eligibility failures are never mixed into the ranking.
4. Always include the disclaimer: the score orders attention; it is not a probability of winning.
5. Suggest `/match <id>` for the top candidates and `/verify <id>` for any that are not `officially_confirmed`.
