"""
Unit tests for Phase 8 Gemini Client Layer (Mocked SDK - No Network Calls)
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.gemini_client import (
    is_gemini_configured,
    get_gemini_client,
    generate_grounded_response
)


def test_missing_api_key():
    """Test behavior when GEMINI_API_KEY is not set."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        assert is_gemini_configured() is False
        assert get_gemini_client() is None
        assert generate_grounded_response("What to focus on?", {}) is None


def test_configured_api_key():
    """Test is_gemini_configured returns True when GEMINI_API_KEY is present."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_123"}):
        assert is_gemini_configured() is True


def test_mocked_gemini_response():
    """Test generate_grounded_response with mocked SDK response."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Milk 1L is at critical stock-out risk with 2.4 days remaining."
    mock_client.models.generate_content.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
        with patch("src.gemini_client.get_gemini_client", return_value=mock_client):
            res = generate_grounded_response(
                "How is Milk 1L performing?",
                {"product_name": "Milk 1L", "days_remaining": 2.4},
                intent="product_status"
            )
            assert res == "Milk 1L is at critical stock-out risk with 2.4 days remaining."


def test_gemini_api_exception_handling():
    """Test generate_grounded_response returns None when API throws an exception."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API Quota Exceeded")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
        with patch("src.gemini_client.get_gemini_client", return_value=mock_client):
            res = generate_grounded_response("What should I focus on?", {})
            assert res is None
