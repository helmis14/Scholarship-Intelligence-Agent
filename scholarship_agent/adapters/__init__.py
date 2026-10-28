"""Dedicated adapters for structured funding databases.

Each adapter reads the provider's own public data interface (a published dataset,
an RSS feed, catalogue pages) through the polite Fetcher, and returns normalized
Opportunity records that keep provider-specific fields in `provider_metadata`.
Providers do not share a schema or lifecycle: see each module's docstring.
"""

from .base import AdapterResult  # noqa: F401
from .campusfrance import CampusFranceAdapter  # noqa: F401
from .daad import DAADAdapter  # noqa: F401
from .erasmus_mundus import ErasmusMundusAdapter  # noqa: F401
from .euraxess import EuraxessAdapter  # noqa: F401
from .grants_at import GrantsAtAdapter  # noqa: F401
from .nsp_india import NSPIndiaAdapter  # noqa: F401

ADAPTERS = {"daad": DAADAdapter, "erasmus_mundus": ErasmusMundusAdapter, "euraxess": EuraxessAdapter,
            "campusfrance": CampusFranceAdapter, "grants_at": GrantsAtAdapter,
            "nsp_india": NSPIndiaAdapter}
__all__ = ["ADAPTERS", "AdapterResult", "CampusFranceAdapter", "DAADAdapter", "ErasmusMundusAdapter", "EuraxessAdapter",
           "GrantsAtAdapter", "NSPIndiaAdapter"]
