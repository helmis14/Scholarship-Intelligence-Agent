# /sources - Source Registry, Coverage, Freshness and Failures

**Input:** optional `--check` (fetches every source now) or `--add '<json>'`. **Output:** JSON `sources` (freshness, failures, last error), `coverage` (countries with an official source, gaps by region), `search_provider`, `recent_jobs`.

## Steps
1. `python3 -m scholarship_agent sources` (add `--check` to re-test reachability and robots permission).
2. Report: how many sources are healthy, which failed and why, which are stale, the search provider status, and coverage - "N of the countries in the table have a destination-specific official source". List gap regions; offer to add sources for the user's target countries.
3. Add a source only from a URL you have confirmed belongs to the provider:
   `python3 -m scholarship_agent sources --add '{"id":"xx-name","name":"...","url":"https://...","provider":"...","provider_type":"government","source_type":"official","countries":["XX"],"levels":["master"],"kind":"listing","official_domains":["provider.example"]}'`
   (stored in `data/sources.local.json`).
