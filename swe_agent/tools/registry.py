"""Centralized Tool Registry for schema generation and safe dispatching."""

from typing import Any, Optional

from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult
from swe_agent.tools.bash_tool import RunBashCommandTool
from swe_agent.tools.conclusion import ConcludeTaskTool
from swe_agent.tools.editor import CreateFileTool, EditFileReplaceTool, ViewFileTool
from swe_agent.tools.git_tools import GitDiffTool, GitRestoreTool, GitStatusTool
from swe_agent.tools.search import CodeSearchTool, FindSymbolTool, ListDirectoryTool


class ToolRegistry:
    """Registry managing available tools, JSON schemas, and execution routing."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError(f"Tool {tool.__class__.__name__} must define a unique 'name'.")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Look up tool by name."""
        return self._tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """Export all registered tools as OpenAI/Gemini function calling schemas."""
        return [tool.to_function_schema() for tool in self._tools.values()]

    def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        sandbox: AbstractSandbox
    ) -> ToolResult:
        """Safely dispatch execution to registered tool with Pydantic validation."""
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                success=False,
                output=(
                    f"Error: Tool '{name}' does not exist. "
                    f"Available tools: {list(self._tools.keys())}"
                )
            )

        return tool.run(sandbox, **arguments)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


def create_default_registry() -> ToolRegistry:
    """Initialize standard production tool suite."""
    registry = ToolRegistry()

    # Search & Codebase Intelligence
    registry.register(CodeSearchTool())
    registry.register(FindSymbolTool())
    registry.register(ListDirectoryTool())

    # Precision File Editing
    registry.register(ViewFileTool())
    registry.register(EditFileReplaceTool())
    registry.register(CreateFileTool())

    # Safe Version Control
    registry.register(GitDiffTool())
    registry.register(GitStatusTool())
    registry.register(GitRestoreTool())

    # Sandboxed Terminal Execution
    registry.register(RunBashCommandTool())

    # Task Conclusion
    registry.register(ConcludeTaskTool())

    return registry
