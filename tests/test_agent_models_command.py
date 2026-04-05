"""Tests for the /models command in the interactive agent."""

import pytest
from unittest.mock import MagicMock, patch

from agent import _fetch_models, _display_models


class TestFetchModels:
    """Test fetching models from the proxy."""

    def test_fetch_models_success(self):
        """Successfully fetch models from the proxy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "model1", "owned_by": "test"},
                {"id": "model2", "owned_by": "test"},
            ]
        }
        
        with patch("httpx.get", return_value=mock_response):
            models = _fetch_models("http://localhost:8080/v1")
        
        assert len(models) == 2
        assert models[0]["id"] == "model1"
        assert models[1]["id"] == "model2"

    def test_fetch_models_with_api_key(self):
        """Fetch models with authorization header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        
        with patch("httpx.get", return_value=mock_response) as mock_get:
            _fetch_models("http://localhost:8080/v1", api_key="test-key")
        
        call_args = mock_get.call_args
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    def test_fetch_models_failure(self):
        """Return empty list on failure."""
        with patch("httpx.get", side_effect=Exception("Connection error")):
            models = _fetch_models("http://localhost:8080/v1")
        
        assert models == []

    def test_fetch_models_non_200(self):
        """Return empty list on non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        
        with patch("httpx.get", return_value=mock_response):
            models = _fetch_models("http://localhost:8080/v1")
        
        assert models == []


class TestDisplayModels:
    """Test displaying models in a table."""

    def test_display_models_empty(self, capsys):
        """Display message when no models available."""
        from rich.console import Console
        
        console = Console(force_terminal=True)
        
        with patch("agent.console", console):
            _display_models([], "current-model")
        
        # Should not raise an error
        
    def test_display_models_with_data(self):
        """Display models in a table."""
        from rich.console import Console
        
        console = Console(force_terminal=True)
        models = [
            {"id": "model1", "owned_by": "test"},
            {"id": "model2", "owned_by": "test"},
            {"id": "current-model", "owned_by": "test"},
        ]
        
        with patch("agent.console", console):
            # Should not raise an error
            _display_models(models, "current-model")


class TestModelAliases:
    """Test that model aliases are properly documented."""

    def test_common_aliases_exist(self):
        """Common model aliases are defined."""
        from llmproxy.local_provider import MODEL_ALIASES
        
        expected_aliases = [
            "local-coder",
            "local-coder-small",
            "local",
            "local-deepseek",
            "local-codellama",
        ]
        
        for alias in expected_aliases:
            assert alias in MODEL_ALIASES, f"Missing alias: {alias}"
