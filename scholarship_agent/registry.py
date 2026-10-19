"""Configurable source registry and the coverage-gap report."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import countries
from .store import data_dir

SEED = Path(__file__).with_name("sources.json")
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
      "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}


@dataclass
class Source:
    id: str
    name: str
    url: str
    provider: str = ""
    provider_type: str = "other"
    source_type: str = "official"          # official | aggregator
    countries: list[str] = field(default_factory=list)   # ISO codes, "*" global, "*EU" / "*Asia" regional
    eligible_nationalities: list[str] = field(default_factory=list)
    levels: list[str] = field(default_factory=list)
    kind: str = "listing"                  # listing | opportunity | rss
    official_domains: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en"])
    refresh_days: int = 30
    enabled: bool = True
    scope: str = ""                        # international | domestic | both (who it is for, relative to destination)
    notes: str = ""
    # durable official discovery: links (from the page, its sitemap or its feed) whose path matches url_pattern are
    # the programme pages; `sitemap` names the sitemap when it is not at /sitemap.xml or in robots.txt
    url_pattern: str = ""
    sitemap: str = ""

    def destination_codes(self) -> set[str]:
        out: set[str] = set()
        for c in self.countries:
            if c == "*":
                out |= set(countries.COUNTRIES)
            elif c == "*EU":
                out |= EU
            elif c.startswith("*"):
                out |= {k for k, (_, r) in countries.COUNTRIES.items() if r == c[1:]}
            else:
                out.add(c.upper())
        return out

    def is_global(self) -> bool:
        return "*" in self.countries


def _load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get("sources", doc) if isinstance(doc, dict) else doc


def load_sources(local: Optional[Path] = None) -> list[Source]:
    known = {f for f in Source.__dataclass_fields__}
    merged: dict[str, dict] = {s["id"]: s for s in _load(SEED)}
    for s in _load(local or data_dir() / "sources.local.json"):
        merged[s["id"]] = merged.get(s["id"], {}) | s
    return [Source(**{k: v for k, v in s.items() if k in known}) for s in merged.values()]


def add_local_source(entry: dict, local: Optional[Path] = None) -> Path:
    for k in ("id", "name", "url"):
        if not entry.get(k):
            raise ValueError(f"source needs '{k}'")
    if not str(entry["url"]).startswith(("https://", "http://")):
        raise ValueError("source url must be http(s)")
    path = local or data_dir() / "sources.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [s for s in _load(path) if s.get("id") != entry["id"]] + [entry]
    path.write_text(json.dumps({"sources": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def coverage(sources: list[Source], states: dict[str, dict] | None = None) -> dict:
    """Per-country source counts. Global sources (aggregators, worldwide programmes) are
    counted separately: they make a country searchable, not covered."""
    states = states or {}
    per: dict[str, dict] = {c: {"official": 0, "aggregator": 0, "healthy_official": 0} for c in countries.COUNTRIES}
    global_sources, regional_sources = [], []
    for s in sources:
        if not s.enabled:
            continue
        if s.is_global() or any(c.startswith("*") for c in s.countries):
            # worldwide or region-wide programmes make a country searchable, not covered
            (global_sources if s.is_global() else regional_sources).append(s.id)
            continue
        healthy = states.get(s.id, {}).get("consecutive_failures", 0) == 0 and \
            states.get(s.id, {}).get("last_ok") is not None
        for c in s.destination_codes():
            if c in per:
                key = "official" if s.source_type == "official" else "aggregator"
                per[c][key] += 1
                if key == "official" and healthy:
                    per[c]["healthy_official"] += 1
    gaps = sorted(c for c, v in per.items() if v["official"] == 0)
    by_region: dict[str, dict] = {}
    for c, v in per.items():
        r = by_region.setdefault(countries.region(c), {"countries": 0, "with_official_source": 0})
        r["countries"] += 1
        r["with_official_source"] += v["official"] > 0
    return {
        "countries_total": len(per),
        "countries_with_official_source": len(per) - len(gaps),
        "countries_with_verified_healthy_source": sum(1 for v in per.values() if v["healthy_official"]),
        "global_sources": global_sources,
        "regional_sources": regional_sources,
        "by_region": by_region,
        "gaps": [{"code": c, "name": countries.name(c), "region": countries.region(c)} for c in gaps],
        "note": ("A gap means no destination-specific official source is registered. Global/regional sources and web search "
                 "can still surface opportunities there, but nothing about that country has been systematically checked."),
    }
