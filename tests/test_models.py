"""Unit tests for ModelProvider gateway and fallback mechanism."""

from unittest.mock import MagicMock, patch
from swe_agent.models.provider import ModelProvider, ModelResponse


def test_model_provider_initialization():
    """Verify default models are configured properly."""
    provider = ModelProvider()
    assert "gemini" in provider.primary_model
    assert "qwen" in provider.fallback_model


@patch("swe_agent.models.provider.litellm")
def test_model_provider_successful_primary_call(mock_litellm):
    """Verify primary model call and response normalization."""
    # Mock litellm completion response
    mock_choice = MagicMock()
    mock_choice.message.content = "I will inspect the codebase."
    mock_choice.message.tool_calls = []

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 120
    mock_response.usage.completion_tokens = 30
    mock_response.usage.total_tokens = 150

    mock_litellm.completion.return_value = mock_response

    provider = ModelProvider(primary_model="gemini/gemini-3.8-flash")
    messages = [{"role": "user", "content": "Fix issue #12"}]
    res = provider.generate(messages=messages)

    assert res.content == "I will inspect the codebase."
    assert res.prompt_tokens == 120
    assert res.completion_tokens == 30
    assert res.model == "gemini/gemini-3.8-flash"
    assert provider.total_prompt_tokens == 120


@patch("swe_agent.models.provider.litellm")
def test_model_provider_failover_to_fallback(mock_litellm):
    """Verify automatic failover to local fallback when primary fails."""
    # First call (primary) raises error, second call (fallback) succeeds
    mock_choice = MagicMock()
    mock_choice.message.content = "Fallback model response"
    mock_choice.message.tool_calls = []

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 80
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 100

    mock_litellm.completion.side_effect = [
        RuntimeError("Primary cloud API 429 Rate Limit Exceeded"),
        mock_response
    ]

    provider = ModelProvider(
        primary_model="gemini/gemini-3.8-flash",
        fallback_model="ollama/qwen3-coder:latest"
    )
    messages = [{"role": "user", "content": "Fix issue #12"}]
    res = provider.generate(messages=messages)

    assert res.content == "Fallback model response"
    assert res.model == "ollama/qwen3-coder:latest"
