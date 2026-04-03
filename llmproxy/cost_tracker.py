"""Per-API-key cost tracking and budget management."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class APIKeyStats:
    """Statistics for a single API key."""

    api_key: str  # Hashed/key_id, not the actual key
    requests_total: int = 0
    tokens_upstream: int = 0
    tokens_downstream: int = 0
    estimated_cost: float = 0.0  # In USD
    first_seen: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "api_key": self.api_key[:16] + "..." if len(self.api_key) > 16 else self.api_key,
            "requests_total": self.requests_total,
            "tokens_upstream": self.tokens_upstream,
            "tokens_downstream": self.tokens_downstream,
            "estimated_cost": round(self.estimated_cost, 4),
            "first_seen": self.first_seen,
            "last_used": self.last_used,
        }


class CostTracker:
    """Track costs and usage per API key.

    Features:
    - Track token usage per API key
    - Estimate costs based on token pricing
    - Set budgets per API key
    - Alert when budgets are exceeded
    - Persist stats to disk
    """

    # Default pricing per 1K tokens (approximate OpenAI-like pricing)
    DEFAULT_UPSTREAM_PRICE = 0.01  # $0.01 per 1K input tokens
    DEFAULT_DOWNSTREAM_PRICE = 0.03  # $0.03 per 1K output tokens

    def __init__(
        self,
        upstream_price: float = None,
        downstream_price: float = None,
        storage_path: Optional[str] = None,
        auto_save: bool = True,
    ):
        self.upstream_price = upstream_price or self.DEFAULT_UPSTREAM_PRICE
        self.downstream_price = downstream_price or self.DEFAULT_DOWNSTREAM_PRICE
        self.storage_path = Path(storage_path) if storage_path else None
        self.auto_save = auto_save

        self._stats: dict[str, APIKeyStats] = {}
        self._budgets: dict[str, float] = {}  # api_key -> budget in USD
        self._alerts: dict[str, bool] = {}  # api_key -> alert triggered
        self._lock = Lock()

        # Load persisted stats if available
        if self.storage_path and self.storage_path.exists():
            self._load()

    def _get_key_id(self, api_key: str) -> str:
        """Get a safe identifier for an API key (hash it)."""
        import hashlib

        return hashlib.sha256(api_key.encode()).hexdigest()[:16]

    def record_usage(
        self,
        api_key: str,
        upstream_tokens: int,
        downstream_tokens: int,
    ) -> Optional[str]:
        """Record token usage for an API key.

        Args:
            api_key: The API key used
            upstream_tokens: Number of input tokens
            downstream_tokens: Number of output tokens

        Returns:
            Alert message if budget exceeded, None otherwise
        """
        key_id = self._get_key_id(api_key)

        # Calculate cost
        upstream_cost = (upstream_tokens / 1000) * self.upstream_price
        downstream_cost = (downstream_tokens / 1000) * self.downstream_price
        total_cost = upstream_cost + downstream_cost

        with self._lock:
            if key_id not in self._stats:
                self._stats[key_id] = APIKeyStats(api_key=key_id)

            stats = self._stats[key_id]
            stats.requests_total += 1
            stats.tokens_upstream += upstream_tokens
            stats.tokens_downstream += downstream_tokens
            stats.estimated_cost += total_cost
            stats.last_used = time.time()

            # Check budget
            alert = self._check_budget(key_id)

            # Auto-save if enabled
            if self.auto_save and self.storage_path:
                self._save()

            return alert

    def _check_budget(self, key_id: str) -> Optional[str]:
        """Check if API key has exceeded its budget.

        Returns:
            Alert message if budget exceeded, None otherwise
        """
        if key_id not in self._budgets:
            return None

        budget = self._budgets[key_id]
        spent = self._stats[key_id].estimated_cost

        if spent >= budget and not self._alerts.get(key_id):
            self._alerts[key_id] = True
            return (
                f"Budget exceeded: API key {key_id[:8]}... "
                f"has spent ${spent:.2f} of ${budget:.2f} budget"
            )

        # Reset alert if under budget (e.g., after budget increase)
        if spent < budget and self._alerts.get(key_id):
            self._alerts[key_id] = False

        return None

    def set_budget(self, api_key: str, budget_usd: float) -> None:
        """Set a budget for an API key.

        Args:
            api_key: The API key to set budget for
            budget_usd: Budget in USD (0 = no budget)
        """
        key_id = self._get_key_id(api_key)

        with self._lock:
            if budget_usd > 0:
                self._budgets[key_id] = budget_usd
                self._alerts[key_id] = False
                logger.info(f"Set budget ${budget_usd:.2f} for API key {key_id[:8]}...")
            else:
                self._budgets.pop(key_id, None)
                self._alerts.pop(key_id, None)

    def get_budget(self, api_key: str) -> Optional[float]:
        """Get the budget for an API key."""
        key_id = self._get_key_id(api_key)
        return self._budgets.get(key_id)

    def get_stats(self, api_key: Optional[str] = None) -> dict:
        """Get statistics for an API key or all keys.

        Args:
            api_key: Specific API key, or None for all

        Returns:
            Dictionary of stats
        """
        with self._lock:
            if api_key:
                key_id = self._get_key_id(api_key)
                if key_id in self._stats:
                    return self._stats[key_id].to_dict()
                return {}

            # Return all stats
            return {key: stats.to_dict() for key, stats in self._stats.items()}

    def get_summary(self) -> dict:
        """Get summary of all usage."""
        with self._lock:
            total_requests = sum(s.requests_total for s in self._stats.values())
            total_upstream = sum(s.tokens_upstream for s in self._stats.values())
            total_downstream = sum(s.tokens_downstream for s in self._stats.values())
            total_cost = sum(s.estimated_cost for s in self._stats.values())

            return {
                "keys_total": len(self._stats),
                "requests_total": total_requests,
                "tokens_upstream_total": total_upstream,
                "tokens_downstream_total": total_downstream,
                "estimated_cost_total": round(total_cost, 4),
                "budgets_set": len(self._budgets),
            }

    def reset_stats(self, api_key: Optional[str] = None) -> None:
        """Reset statistics for an API key or all keys.

        Args:
            api_key: Specific API key, or None for all
        """
        with self._lock:
            if api_key:
                key_id = self._get_key_id(api_key)
                if key_id in self._stats:
                    del self._stats[key_id]
                    logger.info(f"Reset stats for API key {key_id[:8]}...")
            else:
                self._stats.clear()
                logger.info("Reset all API key stats")

            if self.auto_save and self.storage_path:
                self._save()

    def _save(self) -> None:
        """Persist stats to disk."""
        try:
            data = {
                "stats": {
                    key: {
                        "api_key": stats.api_key,
                        "requests_total": stats.requests_total,
                        "tokens_upstream": stats.tokens_upstream,
                        "tokens_downstream": stats.tokens_downstream,
                        "estimated_cost": stats.estimated_cost,
                        "first_seen": stats.first_seen,
                        "last_used": stats.last_used,
                    }
                    for key, stats in self._stats.items()
                },
                "budgets": self._budgets,
                "pricing": {
                    "upstream": self.upstream_price,
                    "downstream": self.downstream_price,
                },
                "saved_at": time.time(),
            }

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cost tracker data: {e}")

    def _load(self) -> None:
        """Load stats from disk."""
        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            # Load stats
            for key_id, stats_data in data.get("stats", {}).items():
                self._stats[key_id] = APIKeyStats(
                    api_key=stats_data["api_key"],
                    requests_total=stats_data["requests_total"],
                    tokens_upstream=stats_data["tokens_upstream"],
                    tokens_downstream=stats_data["tokens_downstream"],
                    estimated_cost=stats_data["estimated_cost"],
                    first_seen=stats_data["first_seen"],
                    last_used=stats_data["last_used"],
                )

            # Load budgets
            self._budgets = data.get("budgets", {})

            logger.info(f"Loaded cost tracker data for {len(self._stats)} API keys")
        except Exception as e:
            logger.error(f"Failed to load cost tracker data: {e}")


# Global cost tracker instance
COST_TRACKER = CostTracker(
    storage_path="data/cost_tracker.json",
    auto_save=True,
)


def record_api_key_usage(
    api_key: str,
    upstream_tokens: int,
    downstream_tokens: int,
) -> Optional[str]:
    """Convenience function to record usage in global tracker.

    Returns:
        Alert message if budget exceeded
    """
    return COST_TRACKER.record_usage(api_key, upstream_tokens, downstream_tokens)


def check_budget(api_key: str) -> bool:
    """Check if API key has budget remaining.

    Returns:
        True if under budget or no budget set
    """
    budget = COST_TRACKER.get_budget(api_key)
    if budget is None:
        return True

    stats = COST_TRACKER.get_stats(api_key)
    if not stats:
        return True

    return stats["estimated_cost"] < budget
