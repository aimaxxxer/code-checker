"""Marketplace and data providers.

Every provider exposes the same surface so the server can swap sources without
the scoring engine noticing.
"""

from .base import ProviderError, SupplierProvider

__all__ = ["ProviderError", "SupplierProvider"]
