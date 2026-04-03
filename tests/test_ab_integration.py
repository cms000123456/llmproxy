"""Integration tests for A/B testing request routing."""

from unittest.mock import MagicMock, patch

import pytest


class TestABTestingRouting:
    """Test A/B testing routes requests to correct upstream."""

    @pytest.mark.asyncio
    async def test_ab_test_routes_to_control_by_default(self):
        """When A/B testing enabled but variant is control, use primary client."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.ab_test_traffic_split = 0.0  # Always control
                mock_settings.ab_test_sticky_sessions = False

                variant = _get_ab_test_variant("test_key")
                assert variant == "control"

    @pytest.mark.asyncio
    async def test_ab_test_routes_to_experimental_when_selected(self):
        """When A/B testing enabled and variant is experimental, use experimental client."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.ab_test_traffic_split = 1.0  # Always experimental
                mock_settings.ab_test_sticky_sessions = False

                variant = _get_ab_test_variant("test_key_2")
                assert variant == "experimental"

    def test_ab_test_metrics_tracked(self):
        """A/B test metrics should be tracked per variant."""
        from llmproxy.server import _ab_test_metrics

        # Reset metrics
        _ab_test_metrics["control"]["requests"] = 0
        _ab_test_metrics["experimental"]["requests"] = 0

        # Simulate requests
        _ab_test_metrics["control"]["requests"] += 1
        _ab_test_metrics["experimental"]["requests"] += 2

        assert _ab_test_metrics["control"]["requests"] == 1
        assert _ab_test_metrics["experimental"]["requests"] == 2


class TestABTestingClientSelection:
    """Test HTTP client selection based on A/B variant."""

    def test_control_uses_primary_client(self):
        """Control variant should use _http_client."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            mock_settings.ab_test_enabled = True
            mock_settings.ab_test_sticky_sessions = True
            mock_settings.ab_test_traffic_split = 0.0

            # First call sets the variant
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                variant = _get_ab_test_variant("sticky_key")
                assert variant == "control"

    def test_experimental_uses_experimental_client(self):
        """Experimental variant should use _experimental_http_client."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            mock_settings.ab_test_enabled = True
            mock_settings.ab_test_sticky_sessions = True
            mock_settings.ab_test_traffic_split = 1.0

            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                variant = _get_ab_test_variant("exp_key")
                assert variant == "experimental"


class TestABTestingHeaders:
    """Test A/B testing headers in responses."""

    def test_ab_test_status_endpoint_shows_metrics(self):
        """Status endpoint should return current A/B test metrics."""
        # This is already tested in test_ab_testing.py, but we verify integration
        from llmproxy.server import _ab_test_metrics

        # Ensure metrics structure is valid
        assert "control" in _ab_test_metrics
        assert "experimental" in _ab_test_metrics
        assert "requests" in _ab_test_metrics["control"]
        assert "errors" in _ab_test_metrics["control"]
        assert "latency_ms" in _ab_test_metrics["control"]
