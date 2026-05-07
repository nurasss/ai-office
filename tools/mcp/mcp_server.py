"""MCP Server — регистрация и экспозиция инструментов офиса."""

from typing import Any, Callable

from core.logger import get_logger

logger = get_logger("tools.mcp.server")

class MCPServer:
    """MCP-сервер для регистрации инструментов ИИ-офиса.

    Позволяет экспонировать внутренние инструменты (тулзы агентов)
    через стандартный MCP-протокол.
    """

    def __init__(self, name: str = "ai-office", version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Зарегистрировать инструмент.

        Args:
            name: уникальное имя инструмента.
            description: описание для LLM.
            parameters: JSON Schema параметров.
            handler: функция-обработчик.
        """
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
        }
        logger.info("mcp.register_tool", name=name)

    def list_tools(self) -> list[dict[str, Any]]:
        """Список всех зарегистрированных инструментов."""
        return [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in self._tools.values()
        ]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Выполнить зарегистрированный инструмент.

        Args:
            tool_name: имя инструмента.
            arguments: параметры.

        Returns:
            Результат выполнения.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        logger.info("mcp.execute", tool=tool_name, args=arguments)
        result = await tool["handler"](**arguments) if callable(tool["handler"]) else None
        return {"status": "ok", "tool": tool_name, "result": result}
