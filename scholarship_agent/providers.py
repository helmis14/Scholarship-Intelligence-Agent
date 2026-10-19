"""Official-provider registry: which domains belong to known funders, with provenance and an explicit trust level.

Trust levels (strongest first):
  registry_official   the domain is an official domain of a source in sources.json or sources.local.json
  reviewed_official   a person accepted the domain after reviewing it (stored as a local source, with the note)
  pattern_official    the host has a government / academic / intergovernmental suffix (.gov, .go.id, .gouv.fr,
                      .ac.jp, .edu, .int ...). Treated as official by the existing checks, but nobody confirmed
                      *which* organisation it is
  candidate           a domain that yielded an opportunity page and is in none of the above: recorded for review,
                      never trusted automatically - mentioning "scholarship" or resembling an official name is not
                      proof
  rejected            reviewed and rejected
"""

from __future__ import annotations

import json
from typing import Optional

from .discovery import OFFICIAL_TLD, host_of
from .registry import Source, add_local_source
from .store import Store, now


def official_registry(sources: list[Source]) -> dict[str, dict]:
    """domain -> {provider, sources, countries, provider_type, provenance, trust}"""
    out: dict[str, dict] = {}
    for s in sources:
        for d in s.official_domains or []:
            d = d.lower().removeprefix("www.")
            row = out.setdefault(d, {"provider": s.provider or s.name, "sources": [], "countries": set(),
                                     "provider_type": s.provider_type,
                                     "trust": "reviewed_official" if getattr(s, "notes", "").startswith("reviewed")
                                     else "registry_official",
                                     "provenance": "sources.local.json" if s.id.startswith("reviewed-") else "sources.json"})
            row["sources"].append(s.id)
            row["countries"] |= set(s.countries or [])
    for row in out.values():
        row["countries"] = sorted(row["countries"])
    return out


def classify_domain(url: str, sources: list[Source], store: Optional[Store] = None) -> tuple[str, dict]:
    """(trust level, details) for the host of `url`."""
    host = host_of(url)
    reg = official_registry(sources)
    for d, row in reg.items():
        if host == d or host.endswith("." + d):
            return row["trust"], {"domain": d, **row}
    if store is not None:
        r = store.catalog.execute("SELECT status FROM provider_candidates WHERE domain=?", (host,)).fetchone()
        if r and r["status"] == "rejected":
            return "rejected", {"domain": host}
    if OFFICIAL_TLD.search(host):
        return "pattern_official", {"domain": host, "provenance": "host suffix", "confirmed": False}
    return "candidate", {"domain": host}


def note_candidate(store: Store, url: str, country: str, opp, sources: list[Source]) -> Optional[str]:
    """Record the domain of a page that yielded an opportunity, unless the registry already knows it.
    Returns the trust level when a candidate row was written or updated."""
    trust, info = classify_domain(url, sources, store)
    if trust in ("registry_official", "reviewed_official", "rejected"):
        return None
    host = info["domain"]
    signals = {"pattern_official": trust == "pattern_official", "page_authority": getattr(opp, "source_authority", ""),
               "provider_name": getattr(opp, "provider_name", ""), "title": (getattr(opp, "title", "") or "")[:120]}
    row = store.catalog.execute("SELECT * FROM provider_candidates WHERE domain=?", (host,)).fetchone()
    with store.catalog as c:
        if row:
            urls = json.loads(row["sample_urls"] or "[]")
            urls = (urls + [url])[-5:] if url not in urls else urls
            cs = sorted(set(json.loads(row["countries"] or "[]")) | ({country} if country else set()))
            c.execute("UPDATE provider_candidates SET last_seen=?, times_seen=times_seen+1, countries=?, sample_urls=?, "
                      "signals=? WHERE domain=?", (now(), json.dumps(cs), json.dumps(urls), json.dumps(signals), host))
        else:
            c.execute("INSERT INTO provider_candidates VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (host, now(), now(), 1, json.dumps([country] if country else []), json.dumps([url]),
                       json.dumps(signals), "candidate", None, None))
    return trust


def candidates(store: Store, status: str = "candidate", limit: int = 100) -> list[dict]:
    rows = store.catalog.execute("SELECT * FROM provider_candidates WHERE status=? ORDER BY times_seen DESC, domain "
                                 "LIMIT ?", (status, limit)).fetchall()
    return [dict(r) | {"countries": json.loads(r["countries"] or "[]"), "sample_urls": json.loads(r["sample_urls"] or "[]"),
                       "signals": json.loads(r["signals"] or "{}")} for r in rows]


def review(store: Store, domain: str, accept: bool, provider: str = "", note: str = "",
           provider_type: str = "other") -> dict:
    """A person's decision on a candidate. Accepting adds a local source whose official domain is `domain`."""
    domain = domain.lower().removeprefix("www.")
    row = store.catalog.execute("SELECT * FROM provider_candidates WHERE domain=?", (domain,)).fetchone()
    if not row:
        raise ValueError(f"no candidate {domain!r}")
    if accept and not provider:
        raise ValueError("accepting needs --provider (the organisation the domain belongs to)")
    with store.catalog as c:
        c.execute("UPDATE provider_candidates SET status=?, reviewed_at=?, note=? WHERE domain=?",
                  ("accepted" if accept else "rejected", now(), note or None, domain))
    if accept:
        urls = json.loads(row["sample_urls"] or "[]")
        add_local_source({"id": f"reviewed-{domain}", "name": provider, "provider": provider,
                          "provider_type": provider_type, "source_type": "official", "kind": "listing",
                          "url": urls[0] if urls else f"https://{domain}/", "official_domains": [domain],
                          "countries": json.loads(row["countries"] or "[]"),
                          "notes": f"reviewed {now()[:10]}: {note}".strip()})
    return {"domain": domain, "status": "accepted" if accept else "rejected"}
