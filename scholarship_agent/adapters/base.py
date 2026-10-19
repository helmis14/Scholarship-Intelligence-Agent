"""Shared adapter result type."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Opportunity


@dataclass
class AdapterResult:
    adapter: str
    records: list[Opportunity] = field(default_factory=list)
    requests: int = 0
    failures: list[dict] = field(default_factory=list)
    leads: list[dict] = field(default_factory=list)       # URLs worth a look that are not records themselves
    notes: list[str] = field(default_factory=list)
    access_method: str = ""

    def summary(self) -> dict:
        return {"adapter": self.adapter, "access_method": self.access_method, "records": len(self.records),
                "requests": self.requests, "failures": self.failures, "leads": len(self.leads), "notes": self.notes}
