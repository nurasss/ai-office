"""ERP / Invoice MCP tool — заглушки для парсинга документов."""

from typing import Any

from langchain_core.tools import tool

@tool
async def parse_invoice_pdf(
    file_path: str,
    extract_tables: bool = True,
) -> dict[str, Any]:
    """Распарсить PDF-инвойс и извлечь структурированные данные.

    Args:
        file_path: путь к PDF-файлу.
        extract_tables: извлечь табличные данные.

    Returns:
        Структурированные данные инвойса:
        номер, дата, поставщик, позиции, суммы, НДС.
    """
    # TODO: реализовать через pypdf + tabula-py
    return {
        "status": "stub",
        "file_path": file_path,
        "invoice_number": None,
        "date": None,
        "vendor": None,
        "items": [],
        "subtotal": 0.0,
        "tax": 0.0,
        "total": 0.0,
        "currency": "USD",
        "message": "Заглушка: установите pypdf и tabula-py",
    }
