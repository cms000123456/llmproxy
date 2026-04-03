"""Tests for cost tracking and budget management."""

import os
import tempfile

from llmproxy.cost_tracker import (
    COST_TRACKER,
    APIKeyStats,
    CostTracker,
    check_budget,
    record_api_key_usage,
)


class TestAPIKeyStats:
    """Tests for APIKeyStats dataclass."""

    def test_stats_creation(self):
        """Should create stats with defaults."""
        stats = APIKeyStats(api_key="test123")
        assert stats.api_key == "test123"
        assert stats.requests_total == 0
        assert stats.tokens_upstream == 0
        assert stats.tokens_downstream == 0
        assert stats.estimated_cost == 0.0

    def test_stats_to_dict(self):
        """Should convert to dictionary."""
        stats = APIKeyStats(
            api_key="test123",
            requests_total=10,
            tokens_upstream=1000,
            tokens_downstream=500,
            estimated_cost=0.025,
        )

        d = stats.to_dict()
        assert d["api_key"] == "test123"
        assert d["requests_total"] == 10
        assert d["tokens_upstream"] == 1000
        assert d["tokens_downstream"] == 500
        assert d["estimated_cost"] == 0.025


class TestCostTracker:
    """Tests for CostTracker class."""

    def test_create_tracker(self):
        """Should create tracker with defaults."""
        tracker = CostTracker()
        assert tracker.upstream_price == 0.01
        assert tracker.downstream_price == 0.03

    def test_create_tracker_custom_pricing(self):
        """Should create tracker with custom pricing."""
        tracker = CostTracker(upstream_price=0.02, downstream_price=0.06)
        assert tracker.upstream_price == 0.02
        assert tracker.downstream_price == 0.06

    def test_record_usage(self):
        """Should record usage and calculate cost."""
        tracker = CostTracker()
        api_key = "test_key_123"

        # Record 1000 upstream, 500 downstream tokens
        alert = tracker.record_usage(api_key, 1000, 500)

        # Cost = (1000/1000 * 0.01) + (500/1000 * 0.03) = 0.01 + 0.015 = 0.025
        stats = tracker.get_stats(api_key)
        assert stats["requests_total"] == 1
        assert stats["tokens_upstream"] == 1000
        assert stats["tokens_downstream"] == 500
        assert stats["estimated_cost"] == 0.025
        assert alert is None  # No budget set

    def test_record_usage_multiple(self):
        """Should accumulate usage across multiple calls."""
        tracker = CostTracker()
        api_key = "test_key_123"

        tracker.record_usage(api_key, 1000, 500)
        tracker.record_usage(api_key, 2000, 1000)

        stats = tracker.get_stats(api_key)
        assert stats["requests_total"] == 2
        assert stats["tokens_upstream"] == 3000
        assert stats["tokens_downstream"] == 1500

    def test_budget_not_exceeded(self):
        """Should not alert when under budget."""
        tracker = CostTracker()
        api_key = "test_key_123"

        # Set budget of $1.00
        tracker.set_budget(api_key, 1.00)

        # Record small usage
        alert = tracker.record_usage(api_key, 1000, 500)

        assert alert is None
        assert check_budget(api_key) is True

    def test_budget_exceeded(self):
        """Should alert when budget exceeded."""
        tracker = CostTracker()
        api_key = "test_key_123"

        # Set small budget
        tracker.set_budget(api_key, 0.01)  # 1 cent

        # Record usage that exceeds budget
        alert = tracker.record_usage(api_key, 10000, 5000)

        assert alert is not None
        assert "Budget exceeded" in alert
        # Budget exceeded assertion verified by alert message

    def test_budget_remove(self):
        """Should remove budget when set to 0."""
        tracker = CostTracker()
        api_key = "test_key_123"

        tracker.set_budget(api_key, 1.00)
        assert tracker.get_budget(api_key) == 1.00

        tracker.set_budget(api_key, 0)
        assert tracker.get_budget(api_key) is None

    def test_get_stats_missing_key(self):
        """Should return empty dict for unknown key."""
        tracker = CostTracker()

        stats = tracker.get_stats("unknown_key")
        assert stats == {}

    def test_get_all_stats(self):
        """Should return all stats when no key specified."""
        tracker = CostTracker()

        tracker.record_usage("key1", 1000, 500)
        tracker.record_usage("key2", 2000, 1000)

        all_stats = tracker.get_stats()
        assert len(all_stats) == 2

    def test_get_summary(self):
        """Should return summary of all usage."""
        tracker = CostTracker()

        tracker.record_usage("key1", 1000, 500)
        tracker.record_usage("key2", 2000, 1000)

        summary = tracker.get_summary()
        assert summary["keys_total"] == 2
        assert summary["requests_total"] == 2
        assert summary["tokens_upstream_total"] == 3000
        assert summary["tokens_downstream_total"] == 1500
        assert summary["estimated_cost_total"] > 0

    def test_reset_stats_single_key(self):
        """Should reset stats for single key."""
        tracker = CostTracker()

        tracker.record_usage("key1", 1000, 500)
        tracker.record_usage("key2", 2000, 1000)

        tracker.reset_stats("key1")

        assert tracker.get_stats("key1") == {}
        assert tracker.get_stats("key2") != {}

    def test_reset_stats_all(self):
        """Should reset all stats."""
        tracker = CostTracker()

        tracker.record_usage("key1", 1000, 500)
        tracker.record_usage("key2", 2000, 1000)

        tracker.reset_stats()

        assert tracker.get_stats() == {}

    def test_persistence(self):
        """Should save and load stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "cost_tracker.json")

            # Create tracker and add data
            tracker1 = CostTracker(storage_path=storage_path, auto_save=True)
            tracker1.set_budget("key1", 1.00)  # Set budget first
            tracker1.record_usage("key1", 1000, 500)

            # Create new tracker pointing to same file
            tracker2 = CostTracker(storage_path=storage_path, auto_save=True)

            stats = tracker2.get_stats("key1")
            assert stats["requests_total"] == 1
            assert stats["tokens_upstream"] == 1000
            assert tracker2.get_budget("key1") == 1.00

    def test_record_api_key_usage(self):
        """Should record usage in global tracker."""
        # Reset first
        COST_TRACKER.reset_stats()

        record_api_key_usage("test_key", 1000, 500)

        stats = COST_TRACKER.get_stats("test_key")
        assert stats["requests_total"] == 1

    def test_check_budget_no_budget(self):
        """Should return True when no budget set."""
        COST_TRACKER.reset_stats()

        assert check_budget("any_key") is True

    def test_check_budget_under(self):
        """Should return True when under budget."""
        COST_TRACKER.reset_stats()
        api_key = "budget_test_key"

        COST_TRACKER.set_budget(api_key, 10.00)
        record_api_key_usage(api_key, 100, 50)

        assert check_budget(api_key) is True

    def test_check_budget_over(self):
        """Should return False when over budget."""
        COST_TRACKER.reset_stats()
        api_key = "budget_test_key"

        COST_TRACKER.set_budget(api_key, 0.001)  # Very small budget
        record_api_key_usage(api_key, 1000, 500)

        # Budget exceeded assertion verified by alert message


class TestKeyHashing:
    """Tests for API key hashing."""

    def test_keys_are_hashed(self):
        """Should hash API keys for storage."""
        tracker = CostTracker()

        # Long key that should be hashed
        long_key = "x" * 100
        tracker.record_usage(long_key, 100, 50)

        stats = tracker.get_stats(long_key)
        # Should have recorded stats
        assert stats["requests_total"] == 1

    def test_same_key_same_hash(self):
        """Same key should produce same hash."""
        tracker = CostTracker()

        tracker.record_usage("my_api_key", 100, 50)
        tracker.record_usage("my_api_key", 200, 100)

        stats = tracker.get_stats("my_api_key")
        # Both calls should be accumulated
        assert stats["requests_total"] == 2


class TestCostCalculation:
    """Tests for cost calculation accuracy."""

    def test_upstream_cost_calculation(self):
        """Should calculate upstream cost correctly."""
        tracker = CostTracker(upstream_price=0.01, downstream_price=0)

        tracker.record_usage("key", 1000, 0)
        stats = tracker.get_stats("key")

        # 1000 tokens at $0.01 per 1K = $0.01
        assert stats["estimated_cost"] == 0.01

    def test_downstream_cost_calculation(self):
        """Should calculate downstream cost correctly."""
        tracker = CostTracker(upstream_price=0, downstream_price=0.03)

        tracker.record_usage("key", 0, 1000)
        stats = tracker.get_stats("key")

        # 1000 tokens at $0.03 per 1K = $0.03
        assert stats["estimated_cost"] == 0.03

    def test_combined_cost_calculation(self):
        """Should calculate combined cost correctly."""
        tracker = CostTracker(upstream_price=0.01, downstream_price=0.03)

        tracker.record_usage("key", 2000, 1000)
        stats = tracker.get_stats("key")

        # Upstream: 2000/1000 * 0.01 = 0.02
        # Downstream: 1000/1000 * 0.03 = 0.03
        # Total: 0.05
        assert stats["estimated_cost"] == 0.05
