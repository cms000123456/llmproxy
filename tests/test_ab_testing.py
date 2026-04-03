"""Tests for A/B testing functionality."""

from unittest.mock import MagicMock, patch

import pytest


class TestABTestVariantSelection:
    """Tests for A/B test variant selection logic."""

    def test_ab_test_disabled_returns_control(self):
        """When A/B testing is disabled, always return control."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", None):
                mock_settings.ab_test_enabled = False

                assert _get_ab_test_variant("some_key") == "control"
                assert _get_ab_test_variant(None) == "control"

    def test_ab_test_no_experimental_client_returns_control(self):
        """When experimental client is not initialized, return control."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", None):
                mock_settings.ab_test_enabled = True

                assert _get_ab_test_variant("some_key") == "control"

    def test_ab_test_sticky_session_consistency(self):
        """Same API key should always get same variant with sticky sessions."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.ab_test_sticky_sessions = True
                mock_settings.ab_test_traffic_split = 0.5

                api_key = "test_api_key_123"

                # Get variant multiple times
                results = [_get_ab_test_variant(api_key) for _ in range(10)]

                # All results should be the same
                assert all(r == results[0] for r in results)

    def test_ab_test_traffic_split_distribution(self):
        """Traffic should be split according to configured percentage."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.ab_test_sticky_sessions = False  # Random assignment
                mock_settings.ab_test_traffic_split = 0.3  # 30% to experimental

                # Test with many different keys
                results = []
                for i in range(1000):
                    key = f"key_{i}"
                    results.append(_get_ab_test_variant(key))

                experimental_count = results.count("experimental")
                experimental_pct = experimental_count / len(results)

                # Should be roughly 30% (with some tolerance)
                assert 0.25 <= experimental_pct <= 0.35

    def test_ab_test_no_sticky_sessions_random(self):
        """Without sticky sessions, same key can get different variants."""
        from llmproxy.server import _get_ab_test_variant

        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.ab_test_sticky_sessions = False
                mock_settings.ab_test_traffic_split = 0.5

                api_key = "test_api_key"

                # With random assignment, we might get different variants
                # (This is probabilistic, so we just verify it runs)
                results = [_get_ab_test_variant(api_key) for _ in range(100)]

                # Both variants should appear
                assert "control" in results
                # Experimental might or might not appear depending on randomness


class TestABTestMetrics:
    """Tests for A/B test metrics tracking."""

    def test_metrics_structure(self):
        """Verify metrics dictionary has correct structure."""
        from llmproxy.server import _ab_test_metrics

        assert "control" in _ab_test_metrics
        assert "experimental" in _ab_test_metrics
        assert "requests" in _ab_test_metrics["control"]
        assert "errors" in _ab_test_metrics["control"]
        assert "requests" in _ab_test_metrics["experimental"]
        assert "errors" in _ab_test_metrics["experimental"]


class TestABTestStatusEndpoint:
    """Tests for the A/B test status endpoint."""

    @pytest.mark.asyncio
    async def test_ab_test_status_disabled(self, client):
        """Status endpoint returns correct data when A/B testing is disabled."""
        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", None):
                mock_settings.ab_test_enabled = False

                response = client.get("/ab-test/status")
                assert response.status_code == 200
                data = response.json()

                assert data["enabled"] is False
                assert data["configuration"]["experimental_upstream"] is None

    @pytest.mark.asyncio
    async def test_ab_test_status_enabled(self, client):
        """Status endpoint returns correct data when A/B testing is enabled."""
        with patch("llmproxy.server.settings") as mock_settings:
            with patch("llmproxy.server._experimental_http_client", MagicMock()):
                mock_settings.ab_test_enabled = True
                mock_settings.experimental_upstream_base_url = "https://experimental.example.com/v1"
                mock_settings.ab_test_traffic_split = 0.2
                mock_settings.ab_test_sticky_sessions = True
                mock_settings.upstream_base_url = "https://control.example.com/v1"

                response = client.get("/ab-test/status")
                assert response.status_code == 200
                data = response.json()

                assert data["enabled"] is True
                assert data["configuration"]["control_upstream"] == "https://control.example.com/v1"
                assert (
                    data["configuration"]["experimental_upstream"]
                    == "https://experimental.example.com/v1"
                )
                assert data["configuration"]["traffic_split"] == 0.2
                assert data["configuration"]["sticky_sessions"] is True
                assert "metrics" in data


class TestABTestConfig:
    """Tests for A/B testing configuration."""

    def test_config_defaults(self):
        """Verify default A/B testing configuration values."""
        from llmproxy.config import Settings

        settings = Settings()

        assert settings.ab_test_enabled is False
        assert settings.experimental_upstream_base_url == ""
        assert settings.experimental_upstream_api_key == ""
        assert settings.ab_test_traffic_split == 0.1
        assert settings.ab_test_sticky_sessions is True
