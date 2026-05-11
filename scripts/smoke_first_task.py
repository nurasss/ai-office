"""Live smoke run for the first AI Office task.

The script verifies the local loop and then calls the routed agent's real LLM:

1. PMO routes the user task.
2. The agent-specific RAG namespaces return scoped context.
3. The routed agent receives system prompt + RAG context + task.

Use --route-only when you want to inspect routing/RAG without spending tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
import re
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents import (
    AccountantAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from agents.base.base_agent import BaseAgent
from core.llm_router import MissingLLMCredentialsError
from rag.retriever import Retriever

DEFAULT_TASK = (
    "Привет, напиши короткий пост о том, что мы запустили ИИ-офис, "
    "и отправь мне черновик"
)

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "accountant": AccountantAgent,
    "copywriter": CopywriterAgent,
    "data_analyst": DataAnalystAgent,
    "developer": DeveloperAgent,
    "strategist": StrategistAgent,
    "support": SupportAgent,
}

MONTH_ORDER = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

QUARTERS = {
    "Q1": ("Январь", "Февраль", "Март"),
    "Q2": ("Апрель", "Май", "Июнь"),
    "Q3": ("Июль", "Август", "Сентябрь"),
    "Q4": ("Октябрь", "Ноябрь", "Декабрь"),
}


async def main() -> None:
    args = parse_args()
    task = args.task or DEFAULT_TASK

    pmo = PMOAgent()
    subtasks = pmo._decompose_task(task)
    assigned_to = subtasks[0]["assigned_to"].value

    pmo_context = await Retriever(agent_id="pmo").retrieve(task)
    agent_context = await Retriever(agent_id=assigned_to).retrieve(task)

    print("AI Office smoke run")
    print("=" * 64)
    print(f"Task: {task}")
    print(f"PMO route: pmo -> {assigned_to}")
    print()
    print_context("PMO RAG context", pmo_context)
    print_context(f"{assigned_to} RAG context", agent_context)

    if args.route_only:
        print(f"Route-only mode: next live agent would be {assigned_to}")
        return

    agent = create_agent(assigned_to)
    rag_text = "\n\n".join(
        str(document.get("content", "")).strip()
        for document in agent_context
        if str(document.get("content", "")).strip()
    )
    full_source_text = read_full_hit_sources(
        agent_context,
        namespace=f"agent_{assigned_to}",
    )
    model_rag_text = full_source_text or rag_text

    try:
        final_result = await agent.process_task(
            task,
            rag_context=model_rag_text,
            use_tools=args.use_tools,
        )
    except MissingLLMCredentialsError as error:
        print("Live LLM call was not started.")
        print(str(error))
        raise SystemExit(2) from error

    if not final_result.strip() and args.offline_fallback:
        fallback_result = build_offline_fallback(
            agent_id=assigned_to,
            task=task,
            rag_text=model_rag_text,
        )
        if fallback_result:
            final_result = fallback_result
    elif not final_result.strip():
        final_result = (
            "LLM вернула пустой ответ. В smoke-режиме инструменты отключены по умолчанию, "
            "поэтому это уже не tool-call. Проверь модель/API-ключи или запусти с "
            "`--offline-fallback`, если хочешь локальный расчет без LLM."
        )

    print("--- ИТОГОВЫЙ ОТВЕТ ---")
    print(final_result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the first live AI Office task.")
    parser.add_argument(
        "task",
        nargs="*",
        help="Task text. Defaults to the AI Office launch post request.",
    )
    parser.add_argument(
        "--route-only",
        action="store_true",
        help="Only print PMO route and RAG hits; do not call the LLM.",
    )
    parser.add_argument(
        "--use-tools",
        action="store_true",
        help="Allow the routed agent to call bound tools. Disabled by default for text-only smoke checks.",
    )
    parser.add_argument(
        "--offline-fallback",
        action="store_true",
        help="If the live model returns empty text, compute a deterministic local answer for supported reports.",
    )
    args = parser.parse_args()
    args.task = " ".join(args.task).strip()
    return args


def create_agent(agent_id: str) -> BaseAgent:
    agent_cls = AGENT_REGISTRY.get(agent_id)
    if not agent_cls:
        raise ValueError(f"Smoke script cannot create agent: {agent_id}")
    return agent_cls()


def print_context(title: str, documents: list[dict]) -> None:
    print(f"{title}: {len(documents)} hit(s)")
    for document in documents:
        metadata = document.get("metadata", {})
        source = metadata.get("source", "unknown")
        namespace = metadata.get("namespace", "unknown")
        score = document.get("score", 0)
        print(f"- namespace={namespace} score={score} source={source}")
    print()


def build_offline_fallback(*, agent_id: str, task: str, rag_text: str) -> str:
    """Return a deterministic local answer when a live model returns empty text."""
    if agent_id != "data_analyst":
        return ""

    task_lower = task.lower()
    if "продаж" not in task_lower or "квартал" not in task_lower:
        return ""

    monthly_sales = extract_monthly_sales(rag_text)
    if not monthly_sales:
        return ""

    required_months = [month for months in QUARTERS.values() for month in months]
    missing_months = [month for month in required_months if month not in monthly_sales]
    if missing_months:
        return ""

    quarter_totals = {}
    for quarter, months in QUARTERS.items():
        quarter_totals[quarter] = {
            "units": sum(monthly_sales[month]["units"] for month in months),
            "revenue": sum(monthly_sales[month]["revenue"] for month in months),
        }

    best_revenue_quarter = max(
        quarter_totals,
        key=lambda quarter: quarter_totals[quarter]["revenue"],
    )
    best_units_quarter = max(
        quarter_totals,
        key=lambda quarter: quarter_totals[quarter]["units"],
    )
    best_revenue_month = max(
        monthly_sales,
        key=lambda month: monthly_sales[month]["revenue"],
    )
    best_month_data = monthly_sales[best_revenue_month]

    q1_requested = (
        "перв" in task_lower
        and ("квартал" in task_lower or "q1" in task_lower)
    )
    month_requested = "месяц" in task_lower or "месяч" in task_lower
    profit_word_requested = "прибыл" in task_lower

    lines = [
        "Модель вернула пустой текст, поэтому smoke-скрипт посчитал ответ локально по RAG-отчету.",
        "",
    ]

    if profit_word_requested:
        lines.extend(
            [
                "В отчете нет себестоимости, маржи или прибыли, поэтому ниже 'прибыльность' трактуется как максимальная выручка.",
                "",
            ]
        )

    if q1_requested:
        lines.extend(
            [
                f"Выручка за первый квартал: `${format_int(quarter_totals['Q1']['revenue'])}`.",
                "",
            ]
        )

    lines.append("Выручка по кварталам:")
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        revenue = f"${format_int(quarter_totals[quarter]['revenue'])}"
        units = format_int(quarter_totals[quarter]["units"])
        lines.append(f"- {quarter}: {revenue}, продано единиц: {units}")

    lines.extend(
        [
            "",
            f"Больше всего выручки вышло в {best_revenue_quarter}: "
            f"`${format_int(quarter_totals[best_revenue_quarter]['revenue'])}`.",
            f"Если под 'продажами' считать количество проданных единиц, лидер тоже {best_units_quarter}: "
            f"{format_int(quarter_totals[best_units_quarter]['units'])} единиц.",
        ]
    )

    if month_requested:
        lines.extend(
            [
                "",
                f"Самый прибыльный месяц по выручке: {best_revenue_month} "
                f"`${format_int(best_month_data['revenue'])}`.",
                f"Показатели месяца: {format_int(best_month_data['units'])} проданных единиц, "
                f"средний чек ${format_int(best_month_data['average_check'])}.",
                f"Почему он вышел самым прибыльным: {infer_best_month_reason(best_revenue_month, monthly_sales, rag_text)}",
            ]
        )
    return "\n".join(lines)


def extract_monthly_sales(text: str) -> dict[str, dict[str, int]]:
    """Extract monthly unit/revenue values from the parsed sales report text."""
    compact = re.sub(r"\s+", " ", text)
    month_pattern = "|".join(MONTH_ORDER)
    matches = list(re.finditer(month_pattern, compact))
    monthly_sales: dict[str, dict[str, int]] = {}

    for index, match in enumerate(matches):
        month = match.group(0)
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(compact)
        segment = compact[match.end():next_start]
        numbers = re.findall(r"\d+", segment)
        parsed = parse_sales_numbers(numbers)
        if parsed:
            units, average_check, revenue = parsed
            monthly_sales[month] = {
                "units": units,
                "average_check": average_check,
                "revenue": revenue,
            }

    return monthly_sales


def read_full_hit_sources(documents: list[dict], *, namespace: str = "") -> str:
    """Read complete local source files for RAG hits when smoke fallback needs them."""
    blocks: list[str] = []
    seen_sources: set[str] = set()
    for document in documents:
        metadata = document.get("metadata", {})
        if namespace and metadata.get("namespace") != namespace:
            continue
        source = str(metadata.get("source") or "")
        if not source or source in seen_sources:
            continue
        seen_sources.add(source)
        path = PROJECT_ROOT / source
        if not path.exists() or not path.is_file():
            continue
        try:
            blocks.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            blocks.append(path.read_text(encoding="utf-8-sig"))
    return "\n\n".join(blocks)


def parse_sales_numbers(numbers: list[str]) -> Optional[tuple[int, int, int]]:
    """Parse row numbers produced by PDF text extraction.

    Rows look like:
    - Январь 450 120 54 000
    - Декабрь 1 100 160 176 000
    """
    if len(numbers) < 4:
        return None

    if len(numbers) >= 5 and len(numbers[1]) == 3:
        units = int(numbers[0] + numbers[1])
        average_check = int(numbers[2])
        revenue = int(numbers[3] + numbers[4].zfill(3))
        return units, average_check, revenue

    units = int(numbers[0])
    average_check = int(numbers[1])
    revenue = int(numbers[2] + numbers[3].zfill(3))
    return units, average_check, revenue


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def infer_best_month_reason(
    month: str,
    monthly_sales: dict[str, dict[str, int]],
    report_text: str,
) -> str:
    """Explain why the top revenue month won using report notes and metrics."""
    data = monthly_sales[month]
    reasons: list[str] = []
    compact_report = re.sub(r"\s+", " ", report_text).lower()

    if month == "Декабрь" and "празднич" in compact_report:
        reasons.append("в отчете прямо указано на праздничный сезон и декабрьский всплеск продаж")

    max_units = max(monthly_sales.values(), key=lambda row: row["units"])["units"]
    max_average_check = max(monthly_sales.values(), key=lambda row: row["average_check"])["average_check"]
    if data["units"] == max_units:
        reasons.append(f"это максимум по количеству продаж: {format_int(data['units'])} единиц")
    if data["average_check"] == max_average_check:
        reasons.append(f"это максимум по среднему чеку: ${format_int(data['average_check'])}")

    if not reasons:
        reasons.append(
            "сочетание количества продаж и среднего чека дало максимальную выручку среди месяцев"
        )

    return "; ".join(reasons) + "."


if __name__ == "__main__":
    asyncio.run(main())
