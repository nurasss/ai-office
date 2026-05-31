"""Read-only SQL tool adapter."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import text

from core.db import get_engine
from tools.base import ToolContext, ToolResult, ToolRisk


FORBIDDEN_SQL = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "EXEC",
    "CALL",
}


def validate_readonly_sql(query: str) -> tuple[bool, str]:
    normalized = query.strip()
    if not normalized:
        return False, "SQL query is empty."
    if ";" in normalized.rstrip(";"):
        return False, "Multiple SQL statements are not allowed."
    first = normalized.split(None, 1)[0].upper()
    if first not in {"SELECT", "WITH", "EXPLAIN"}:
        return False, "Only SELECT/WITH/EXPLAIN statements are allowed."
    tokens = set(re.findall(r"\b[A-Za-z_]+\b", normalized.upper()))
    blocked = sorted(tokens & FORBIDDEN_SQL)
    if blocked:
        return False, f"Forbidden SQL keyword: {blocked[0]}"
    return True, "SQL is read-only."


class SQLReadOnlyTool:
    name = "sql_readonly.query"
    description = "Execute a single read-only SELECT/WITH query with a row limit."
    risk_level = ToolRisk.SAFE_READ
    requires_approval = False

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        query = str(args.get("query", ""))
        ok, reason = validate_readonly_sql(query)
        return ToolResult(
            ok=ok,
            data={"query_hash": _query_hash(query), "limit": _limit(args)},
            message=reason if ok else None,
            error=None if ok else reason,
        )

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        dry = self.dry_run(args, context)
        if not dry.ok:
            return dry
        query = str(args.get("query", "")).rstrip(";")
        limit = _limit(args)
        limited_query = f"SELECT * FROM ({query}) AS ai_office_readonly_subquery LIMIT {limit}"
        try:
            with get_engine().connect() as connection:
                result = connection.execute(text(limited_query))
                rows = [dict(row._mapping) for row in result.fetchmany(limit)]
                columns = list(result.keys())
        except Exception as error:
            return ToolResult(ok=False, data=dry.data, error=str(error))
        return ToolResult(
            ok=True,
            data={**dry.data, "columns": columns, "rows": rows, "row_count": len(rows)},
            message="Read-only SQL query executed.",
        )


def _limit(args: dict[str, Any]) -> int:
    try:
        return max(min(int(args.get("limit", 100)), 1000), 1)
    except (TypeError, ValueError):
        return 100


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
