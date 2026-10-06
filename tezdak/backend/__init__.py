"""Operational stores (tickets, customers, orders, events, flags, settings) used by the features."""

from .facade import Backend

__all__ = ["Backend"]
