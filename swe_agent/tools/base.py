"""Base Tool specification with Pydantic validation and schema generation."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from swe_agent.sandbox.protocol import AbstractSandbox


class ToolResult(BaseModel):
    """Normalized response returned by all agent tools."""

    success: bool = Field(description="Whether the tool execution succeeded")
    output: str = Field(description="Human/LLM readable output text or error message")
    data: Optional[dict[str, Any]] = Field(default=None, description="Structured metadata if any")

    def __str__(self) -> str:
        return self.output


class BaseTool(ABC):
    """Abstract base class for all agent tools.

    Provides automatic generation of OpenAI / Gemini / LiteLLM function calling
    schemas directly from Pydantic input models.
    """

    name: str = ""
    description: str = ""
    args_schema: Type[BaseModel] = BaseModel

    @abstractmethod
    def execute(self, sandbox: AbstractSandbox, **kwargs: Any) -> ToolResult:
        """Execute the tool against the active sandbox environment."""
        pass

    def to_function_schema(self) -> dict[str, Any]:
        """Generate OpenAI/Gemini compatible function calling JSON schema.

        Extracts property types, descriptions, and required fields directly
        from the Pydantic `args_schema`.
        """
        json_schema = self.args_schema.model_json_schema()

        # Clean schema for LLM function calling spec
        properties = json_schema.get("properties", {})
        required = json_schema.get("required", [])

        # Strip internal schema metadata not needed by LLM
        for prop in properties.values():
            prop.pop("title", None)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description.strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def run(self, sandbox: AbstractSandbox, **kwargs: Any) -> ToolResult:
        """Validate input arguments and safely execute tool."""
        try:
            validated_args = self.args_schema(**kwargs)
            return self.execute(sandbox, **validated_args.model_dump())
        except Exception as exc:
            return ToolResult(
                success=False,
                output=f"Error executing tool '{self.name}': {str(exc)}"
            )
