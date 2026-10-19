"""Scholarship Intelligence Agent: discovery, verification, eligibility, ranking,
documents and tracking for scholarships worldwide. Stdlib only.

Entry points: `python3 -m scholarship_agent` (CLI) and
`scholarship_agent.service.ScholarshipService` (integration boundary).
"""

from .models import SCHEMA_VERSION  # noqa: F401  (re-exported)

__all__ = ["SCHEMA_VERSION"]
