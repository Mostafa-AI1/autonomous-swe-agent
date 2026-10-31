"""Model Gateway supporting Gemini 3.8 Flash and Qwen3-Coder via unified interface."""

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

try:
    import litellm
    # Suppress verbose debug logs from litellm
    litellm.suppress_debug_info = True
except ImportError:
    litellm = None

from swe_agent.config import settings

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    """Normalized tool call representation."""
    id: str
    name: str
    arguments: dict[str, Any]


class ModelResponse(BaseModel):
    """Normalized response returned from model providers."""
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    model: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ModelProvider:
    """Decoupled model gateway supporting Gemini 3.8 Flash and local Qwen3-Coder."""

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
        temperature: float | None = None
    ):
        self.primary_model = primary_model or settings.primary_model
        self.fallback_model = fallback_model or settings.fallback_model
        self.temperature = temperature if temperature is not None else settings.model_temperature

        # Cumulative token and cost tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model_override: str | None = None
    ) -> ModelResponse:
        """Call LLM with automatic tool schemas and normalized response extraction.

        Attempts primary model (e.g. Gemini 3.8 Flash) first.
        On network/auth failure, falls back to local model (e.g. Qwen3-Coder via Ollama).
        """
        if litellm is None:
            raise ImportError(
                "LiteLLM is required for model orchestration. "
                "Install it via `pip install litellm`."
            )

        selected_model = model_override or self.primary_model
        start_time = time.perf_counter()

        try:
            return self._call_model(selected_model, messages, tools, start_time)
        except Exception as primary_err:
            logger.warning(
                f"Primary model '{selected_model}' failed ({primary_err}). "
                f"Attempting fallback model '{self.fallback_model}'..."
            )
            try:
                return self._call_model(self.fallback_model, messages, tools, start_time)
            except Exception as fallback_err:
                raise RuntimeError(
                    f"Both primary model ('{selected_model}') and fallback model "
                    f"('{self.fallback_model}') failed.\n"
                    f"Primary error: {primary_err}\n"
                    f"Fallback error: {fallback_err}"
                ) from fallback_err

    def _call_model(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        start_time: float
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        # Configure API base for local Ollama endpoints
        if "ollama" in model_name.lower():
            kwargs["api_base"] = settings.ollama_base_url
        elif "gemini" in model_name.lower() and settings.gemini_api_key:
            kwargs["api_key"] = settings.gemini_api_key

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = litellm.completion(**kwargs)
        duration = time.perf_counter() - start_time

        choice = response.choices[0]
        message = choice.message
        content = message.content

        # Extract tool calls if emitted
        parsed_tool_calls: list[ToolCall] = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                call_id = getattr(tc, "id", f"call_{int(time.time()*1000)}")
                func_name = tc.function.name
                try:
                    args = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
                except json.JSONDecodeError:
                    args = {"raw_arguments": tc.function.arguments}

                parsed_tool_calls.append(
                    ToolCall(id=call_id, name=func_name, arguments=args)
                )

        # Track usage
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) if usage else 0

        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        return ModelResponse(
            content=content,
            tool_calls=parsed_tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=round(duration, 3),
            model=model_name
        )
