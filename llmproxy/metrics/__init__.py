from __future__ import annotations

"""Metrics module for LLM Proxy.

Exports the main Metrics class and the global METRICS instance.
"""

from .metrics import METRICS, Metrics

__all__ = ["Metrics", "METRICS"]
