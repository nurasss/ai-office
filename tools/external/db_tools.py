"""Database MCP tool — заглушки для работы с БД."""

from typing import Any

from langchain_core.tools import tool

@tool
async def run_sql_query(
    query: str,
    database: str = "default",
    limit: int = 1000,
) -> dict[str, Any]:
    """Выполнить SQL-запрос к базе данных.

    Args:
        query: SQL-запрос (SELECT, EXPLAIN, etc.).
        database: имя подключения к БД.
        limit: максимальное число строк результата.

    Returns:
        Результат запроса: колонки + строки.
    """
    # TODO: реализовать через SQLAlchemy + DATABASE_URL
    return {
        "status": "stub",
        "query": query[:200],
        "database": database,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "message": "Заглушка: подключите DATABASE_URL в .env",
    }
