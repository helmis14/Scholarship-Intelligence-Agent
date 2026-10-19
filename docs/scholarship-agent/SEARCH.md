# Live search setup

The agent works without web search (registry pages, sitemaps, programme section pages, the DAAD /
Erasmus Mundus / EURAXESS adapters). Web search adds discovery beyond the registry. One provider is
enough; set either variable and the agent uses it (`SEARCH_PROVIDER=searxng|brave|none` to choose).

## Option A - self-hosted SearXNG (free, recommended)

SearXNG is an open-source metasearch engine that queries other engines and returns their results as JSON.
The repository ships a ready configuration in `deploy/searxng/` for the official `searxng/searxng` image.

```bash
deploy/searxng/start.sh            # port 8080 by default: deploy/searxng/start.sh 8888 for another
export SEARCH_PROVIDER=searxng SEARXNG_URL=http://127.0.0.1:8080
python3 -m scholarship_agent search-check --query "beasiswa S2 luar negeri"
deploy/searxng/stop.sh             # stop and remove the container (configuration is kept)
```

What `start.sh` does:
- copies `deploy/searxng/settings.yml` to `~/.config/scholarship-agent/searxng/settings.yml` on first run (persistent;
  edit it there) and fills in a random `secret_key` (file mode 600, never in the repository);
- runs the container with `--restart unless-stopped`, published on **127.0.0.1 only** (not reachable from other
  machines), and waits for `/healthz`.

The configuration keeps SearXNG's defaults and changes: JSON output on (`search.formats: [html, json]`), the
bot limiter off (it is meant for public instances and would block the agent; safe because only localhost can
reach it), image proxy off, outgoing timeout 4 s per engine (10 s max), connection pool 50/10, HTTP/2, and these
engines enabled: duckduckgo, bing, brave, mojeek, startpage, qwant, wikipedia, alongside the defaults. Results are
not cached by SearXNG; the agent caches every query itself (`requery_days`, default 14) and throttles to one
query per 2 s.

Troubleshooting:
- `docker: command not found` / `daemon not running`: install or start Docker Desktop (or OrbStack / Colima).
- `search-check` says `HTTP 403`: JSON is not enabled; check `formats` in the copied settings file, then re-run
  `start.sh`.
- Few or no results: upstream engines are throttling. The response's `unresponsive_engines` (recorded in the
  strategy report as `engines_unresponsive`) names them. Observed in the 40-query run on 2026-10-17: every
  result came from `google cse` (299) or bing (101); brave was suspended for "too many requests", qwant for
  "access denied", duckduckgo failed certificate validation, wikidata timed out, bing had intermittent connection
  errors, and mojeek and startpage returned nothing.
  Wait, lower `--queries-per-country`, or disable an engine in the settings file.
- Logs: `docker logs scholarship-searxng`. Port taken: `start.sh 8888` and set `SEARXNG_URL` to match.

Updating: `docker pull searxng/searxng:latest && deploy/searxng/start.sh` (the settings file is kept). To pin a
version, set `IMAGE=searxng/searxng:<tag>` in `start.sh`. Read the SearXNG changelog before updating:
settings keys occasionally change.

Trade-offs: no fee, no key, no per-query cap of its own; runs on your machine (~200 MB image). Results depend
on the upstream engines, which rate-limit an instance that sends many queries in a short time, and some return
spam: the agent drops results on IP-address hosts, spam/adult/gambling domains, non-page files and results
with no funding word (in 30+ languages) in title, snippet or URL before fetching anything. Do not expose this
instance publicly; a hosted website needs its own hardened instance (limiter on) and monitoring.

## Option B - Brave Search API (hosted)

1. Create an account and a key at https://api.search.brave.com (choose the plan yourself; Brave has
   offered a free tier with a monthly cap and about 1 query/second - check the current terms).
2. `export BRAVE_SEARCH_API_KEY=...` in your shell profile (never in the repository).
3. `python3 -m scholarship_agent search-check`

Trade-offs: an independent web index with stable JSON and documented limits, no hosting; costs
money beyond the free allowance, and quota is consumed per query and per result page. The agent
throttles to ~1 query/s and caches every query.

## What the agent records

`search-check` stores the provider name, query, timestamp, returned URLs and error (never the key)
in `provider_checks`; every strategy query is logged in `search_queries` with its results in
`search_results`, and every result URL in `discovered_urls` with its status
(new / fetched / opportunity / skipped / failed).

## Country-by-country strategy

```bash
python3 -m scholarship_agent strategy-plan --regions Africa --queries-per-country 4   # no network
python3 -m scholarship_agent strategy-run  --countries ID,KE,PE,FJ --queries-per-country 6 --fetch-per-query 3
python3 -m scholarship_agent coverage      # countries configured vs searched, URLs by status
python3 -m scholarship_agent run-report    # found / retrieved / verified, field level
```

Query categories (priority order): government, university, domestic (citizens-only), local language
(`{local word for scholarship} site:.{ccTLD}`), research, foundation, company, exchange, public agency,
international organisation. Country list = all 231 ISO countries; languages from `search.COUNTRY_LANGS`.
Narrow or extend with `data/discovery_strategy.json` (same keys as the CLI flags).
Searched is not covered: a country counts as searched when at least one query for it succeeded.

## Round 14: localised discovery, coverage, retrieval and targeted Claude

- **Languages:** `scholarship_agent/languages.json` holds concept terms (scholarship, student grant, fully funded,
  tuition waiver, research fellowship, doctoral funding, government, university, international, domestic-only,
  regional), deadline words, month names, number words and duration units for 42 languages, plus each country's
  languages and native name. Add a language there instead of in code.
- **Plan:** `strategy-plan` interleaves provider categories with concept queries in the country's own languages
  ("stipend Norge", "奨学金 日本"); `--concepts` narrows them.
- **Run:** `strategy-run --concurrency 4` fetches pages in parallel across hosts (each host stays serial and
  throttled). URLs left unfetched by an interrupted run are fetched first on the next run; `--resume JOB` continues
  a job from its checkpoint.
- **Coverage:** `coverage-quality` reports countries and languages by status (not attempted / attempted /
  searched / retrieved / yielded / official), categories, domains, retrieval methods, duplicates, Claude usage by
  purpose, gaps and next tasks. A configured country is never reported as covered.
- **Providers:** `provider-candidates` lists domains that yielded opportunities but are not in the registry;
  `provider-review DOMAIN --accept --provider NAME` (or `--reject`) records a person's decision.
- **Browser:** off by default. `SCHOLAR_BROWSER=playwright` (needs `pip install playwright`) renders a page only
  when its HTTP response is a JavaScript shell; logins and CAPTCHAs are never bypassed; renderings are cached.
- **Claude:** discovery asks only for fields the rules left empty (`SCHOLAR_AI_MODE=targeted`, default) with only
  the relevant passages; `ai-plan --set d [--exact-tokens]` shows the requests and costs without sending any.
  `heldout --ai-mode full` keeps the evaluated whole-page path.

## Round 15: search reliability, durable official sources, browser fallback

- **Engine health:** `search-health` shows each SearXNG upstream engine as ready or cooling down and why. Each query
  goes to two healthy engines (a language's own index first: naver for Korean, seznam for Czech), never to all of
  them. Throttle signals double the pause between queries (up to 60 s), clean answers shorten it slowly. Cooldowns
  are at least SearXNG's own suspension (1 h for "too many requests", 24 h for access denied, CAPTCHA or blocked
  TLS) and are stored, so a restart does not hammer a blocked engine. When every engine is cooling down,
  `strategy-run` stops at a checkpoint (`status: paused`) and `--resume JOB` continues later.
- **Not worked around:** engines that refuse us or that the network blocks (DuckDuckGo here) are switched off in
  `deploy/searxng/settings.yml`; no proxies, user-agent rotation or CAPTCHA solving.
- **Durable sources:** a source may set `url_pattern` (which links are programme pages) and `sitemap`; pattern
  sources read the page, its sitemap or its feed (`kind: feed`), fetch this year's and later calls first and keep
  each programme as its own record. Six Norwegian official sources are in `sources.json` (Research Council calls via
  its sitemap, Study in Norway, HK-dir, Lånekassen, NTNU).
- **Browser:** tested on 85 real pages before adding anything: the four pages flagged as JavaScript shells went from
  0 to 4 usable pages with a browser; rendering unflagged pages did not help and sometimes hurt. Install with
  `pip install playwright` and set `SCHOLAR_BROWSER=playwright` (optionally `SCHOLAR_BROWSER_EXECUTABLE` to an
  installed Chromium) to enable it; it stays off by default.
