"""Normalize local raw knowledge exports into agent-specific Markdown sources.

Examples:
    python3 scripts/parse_knowledge_sources.py --agent copywriter
    python3 scripts/parse_knowledge_sources.py --agent support --input ~/Downloads/zendesk
    python3 scripts/parse_knowledge_sources.py --agent all --dry-run
    python3 scripts/parse_knowledge_sources.py --agent accountant --source invoice_templates
    python3 scripts/parse_knowledge_sources.py --init-raw
    python3 scripts/parse_knowledge_sources.py --source-plan
    python3 scripts/parse_knowledge_sources.py --write-source-plan
    python3 scripts/parse_knowledge_sources.py --seed-local
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import json
import re
import shutil
import subprocess
import sys
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from xml.etree import ElementTree

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_CATALOG_PATH = PROJECT_ROOT / "config" / "knowledge_sources.yaml"
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw_knowledge"
SOURCE_PLAN_FILENAME = "SOURCE_PLAN.md"
SOURCE_HINT_FILENAME = "_SOURCE_HINT.md"

SUPPORTED_EXTENSIONS = {
    ".csv",
    ".docx",
    ".htm",
    ".html",
    ".json",
    ".jsonl",
    ".md",
    ".pdf",
    ".pptx",
    ".sql",
    ".txt",
    ".xlsx",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class SourceRecipe:
    source_id: str
    collect: tuple[str, ...]
    systems: tuple[str, ...]
    export_hint: str


@dataclass
class ParsedDocument:
    owner: str
    source_id: str
    input_path: Path
    output_path: Path
    characters: int
    status: str


SOURCE_PROFILES: dict[str, tuple[SourceProfile, ...]] = {
    "common": (
        SourceProfile(
            "company_overview",
            ("company_overview", "company", "about", "о_нас", "about_us"),
            ("mission", "миссия", "product", "продукт", "company", "о компании"),
        ),
        SourceProfile(
            "ai_office_roles",
            ("ai_office_roles", "roles", "agents", "роли", "боты"),
            ("role", "agent", "pmo", "copywriter", "accountant", "роль"),
        ),
        SourceProfile(
            "general_business_processes",
            ("business_processes", "process", "processes", "регламенты"),
            ("process", "workflow", "регламент", "approval", "процесс"),
        ),
        SourceProfile(
            "corporate_tone_of_voice",
            ("tone_of_voice", "tone", "voice", "style", "communication"),
            ("tone of voice", "тон", "стиль", "коммуникац"),
        ),
    ),
    "pmo": (
        SourceProfile(
            "org_structure",
            ("org_structure", "org", "structure", "departments", "оргструктура"),
            ("org", "department", "team", "структур", "отдел", "подчин"),
        ),
        SourceProfile(
            "process_regulations",
            ("process_regulations", "scrum", "kanban", "workflow", "process"),
            ("scrum", "kanban", "workflow", "регламент", "процесс"),
        ),
        SourceProfile(
            "sla_rules",
            ("sla", "sla_rules", "deadlines", "сроки"),
            ("sla", "deadline", "срок", "response time", "время реакции"),
        ),
        SourceProfile(
            "task_tracker_rules",
            ("task_tracker_rules", "jira", "trello", "tracker"),
            ("jira", "trello", "status", "label", "workflow", "статус"),
        ),
        SourceProfile(
            "routing_rules",
            ("routing_rules", "routing", "competency", "matrix", "матрица"),
            ("routing", "competency", "assigned", "маршрут", "компетенц"),
        ),
        SourceProfile(
            "smart_templates",
            ("smart_templates", "smart", "templates", "шаблоны"),
            ("smart", "specific", "measurable", "шаблон", "постановка"),
        ),
    ),
    "copywriter": (
        SourceProfile(
            "brandbook_communications",
            ("brandbook", "brand", "editorial", "redpolicy", "tone"),
            ("brandbook", "tone of voice", "стоп-слова", "редполит", "стиль"),
        ),
        SourceProfile(
            "best_human_content",
            ("examples", "posts", "blog", "telegram", "linkedin", "newsletter"),
            ("post", "article", "email", "newsletter", "пост", "рассыл"),
        ),
        SourceProfile(
            "product_glossary",
            ("glossary", "terms", "terminology", "dictionary", "глоссарий"),
            ("glossary", "term", "definition", "термин", "название"),
        ),
        SourceProfile(
            "pr_templates",
            ("pr_templates", "press", "release", "announcement", "анонс"),
            ("press release", "announcement", "пресс-релиз", "анонс"),
        ),
    ),
    "developer": (
        SourceProfile(
            "code_style_guides",
            ("style_guides", "style", "eslint", "pep8", "coding_standards"),
            ("pep8", "eslint", "lint", "typing", "style guide", "стандарт"),
        ),
        SourceProfile(
            "architecture_schemes",
            ("architecture", "arch", "diagrams", "adr", "архитектура"),
            ("architecture", "service", "backend", "frontend", "архитект"),
        ),
        SourceProfile(
            "api_specs",
            ("api_specs", "api", "openapi", "swagger", "endpoints"),
            ("openapi", "swagger", "endpoint", "api", "schema"),
        ),
        SourceProfile(
            "pull_request_history",
            ("pull_requests", "prs", "pr", "code_review", "review"),
            ("pull request", "code review", "review comment", "pr ", "ревью"),
        ),
    ),
    "support": (
        SourceProfile(
            "faq",
            ("faq", "questions", "help_center", "helpcenter"),
            ("faq", "question", "часто", "вопрос", "ответ"),
        ),
        SourceProfile(
            "successful_tickets",
            ("successful_tickets", "tickets", "zendesk", "intercom", "jira_service"),
            ("ticket", "zendesk", "intercom", "resolution", "тикет"),
        ),
        SourceProfile(
            "user_manuals",
            ("user_manuals", "manual", "guide", "docs", "manuals"),
            ("manual", "guide", "how to", "инструкция", "руководство"),
        ),
        SourceProfile(
            "troubleshooting_guides",
            ("troubleshooting_guides", "troubleshooting", "runbook", "diagnostics"),
            ("troubleshooting", "runbook", "diagnose", "ошибка", "диагност"),
        ),
        SourceProfile(
            "escalation_rules",
            ("escalation_rules", "escalation", "l1", "l2"),
            ("escalation", "l1", "l2", "confidence", "эскалац"),
        ),
    ),
    "data_analyst": (
        SourceProfile(
            "data_dictionaries",
            ("data_dictionaries", "schema", "schemas", "ddl", "dbt", "tables"),
            ("create table", "column", "schema", "dbt", "таблица", "колон"),
        ),
        SourceProfile(
            "kpi_formulas",
            ("kpi_formulas", "kpi", "metrics", "formulas", "метрики"),
            ("kpi", "retention", "ltv", "cac", "roi", "formula", "метрик"),
        ),
        SourceProfile(
            "sql_patterns",
            ("sql_patterns", "sql", "queries", "query_patterns"),
            ("select", "join", "where", "group by", "sql"),
        ),
        SourceProfile(
            "analytics_reports",
            ("report_examples", "reports", "dashboards", "metabase", "tableau"),
            ("dashboard", "report", "metabase", "tableau", "отчет", "дашборд"),
        ),
    ),
    "accountant": (
        SourceProfile(
            "invoice_templates",
            ("document_templates", "invoice", "act", "contract", "templates"),
            ("invoice", "акт", "договор", "contract", "счет", "счёт"),
        ),
        SourceProfile(
            "accounting_policy",
            ("accounting_policy", "accounting", "policy", "учетная"),
            ("accounting policy", "учетная", "учётная", "policy"),
        ),
        SourceProfile(
            "expense_policy",
            ("expense_policy", "expenses", "travel", "reimbursement"),
            ("expense", "travel", "reimbursement", "командиров", "расход"),
        ),
        SourceProfile(
            "legal_entities",
            ("legal_entities", "requisites", "bin", "iin", "bank_details"),
            ("bin", "iin", "iban", "bank", "бин", "иин", "расчетный"),
        ),
        SourceProfile(
            "tax_reference",
            ("tax_reference", "tax", "vat", "nds", "налоги"),
            ("tax", "vat", "ндс", "налог", "ставка"),
        ),
        SourceProfile(
            "chart_of_accounts",
            ("chart_of_accounts", "accounts", "1c", "erp"),
            ("chart of accounts", "account code", "план счетов", "1с"),
        ),
        SourceProfile(
            "approval_matrix",
            ("approval_matrix", "approvals", "limits", "matrix"),
            ("approval", "limit", "threshold", "согласован", "лимит"),
        ),
    ),
    "strategist": (
        SourceProfile(
            "okrs",
            ("okrs", "okr", "goals", "цели"),
            ("okr", "objective", "key result", "цель", "цели"),
        ),
        SourceProfile(
            "roadmaps",
            ("roadmaps", "roadmap", "product_plan", "дорожная"),
            ("roadmap", "milestone", "release", "дорожная карта"),
        ),
        SourceProfile(
            "market_research",
            ("market_research", "market", "research", "gartner", "mckinsey"),
            ("market", "tam", "sam", "som", "industry", "рынок"),
        ),
        SourceProfile(
            "competitor_dossiers",
            ("competitors", "competition", "competitor", "досье"),
            ("competitor", "pricing", "feature comparison", "конкурент"),
        ),
        SourceProfile(
            "business_plans",
            ("business_plans", "business_plan", "investor", "financial_model"),
            ("business plan", "investor", "financial model", "бизнес-план"),
        ),
    ),
}

DEFAULT_SOURCE_BY_OWNER = {
    "common": "company_overview",
    "pmo": "process_regulations",
    "copywriter": "best_human_content",
    "developer": "architecture_schemes",
    "support": "faq",
    "data_analyst": "data_dictionaries",
    "accountant": "invoice_templates",
    "strategist": "market_research",
}

SOURCE_RECIPES: dict[str, dict[str, SourceRecipe]] = {
    "common": {
        "company_overview": SourceRecipe(
            source_id="company_overview",
            collect=(
                "Описание компании: миссия, продукт, аудитория, ценность.",
                "Описание AI Office как продукта и пилота.",
                "Факты, которые можно безопасно подмешивать всем агентам.",
            ),
            systems=(
                "Главная страница сайта компании.",
                "Раздел сайта 'О нас'.",
                "Вводные HR/Onboarding документы из Notion или Confluence.",
            ),
            export_hint=(
                "Сохрани страницы сайта как HTML/PDF или скопируй текст в Markdown. "
                "Из Notion/Confluence лучше экспортировать Markdown или HTML."
            ),
        ),
        "ai_office_roles": SourceRecipe(
            source_id="ai_office_roles",
            collect=(
                "Описание 7 виртуальных сотрудников и границы ответственности.",
                "Правила cross-agent handoff через PMO.",
                "Общие ограничения: human review, no hallucination, source needed.",
            ),
            systems=(
                "Внутренние onboarding документы.",
                "Описание оргструктуры и ролей в Notion/Confluence.",
                "Документы проекта AI Office.",
            ),
            export_hint="Экспортируй Markdown/HTML или положи локальный .md/.txt файл.",
        ),
        "general_business_processes": SourceRecipe(
            source_id="general_business_processes",
            collect=(
                "Общие регламенты работы компании.",
                "Процессы согласования, review, публикации и передачи задач.",
                "Правила работы с внутренними документами и источниками.",
            ),
            systems=(
                "Корпоративный Notion или Confluence.",
                "Onboarding guide.",
                "Внутренние регламенты и wiki.",
            ),
            export_hint="Экспортируй как Markdown, HTML или PDF.",
        ),
        "corporate_tone_of_voice": SourceRecipe(
            source_id="corporate_tone_of_voice",
            collect=(
                "Общий Tone of Voice компании.",
                "Как обращаться к пользователю: на ты или на вы.",
                "Общие правила коммуникации, которые полезны всем агентам.",
            ),
            systems=(
                "Brandbook.",
                "HR/onboarding документы.",
                "Разделы wiki о коммуникации.",
            ),
            export_hint="Положи brand/tone документы в Markdown, PDF, HTML или DOCX.",
        ),
    },
    "pmo": {
        "org_structure": SourceRecipe(
            source_id="org_structure",
            collect=(
                "Оргструктура: кто кому подчиняется.",
                "Матрица компетенций: какой отдел за что отвечает.",
                "Список ответственных людей или ролей для эскалаций.",
            ),
            systems=(
                "Confluence/Notion wiki.",
                "HR onboarding guide.",
                "Оргструктура компании в таблице или презентации.",
            ),
            export_hint="Подойдет PDF, DOCX, CSV, XLSX или Markdown.",
        ),
        "process_regulations": SourceRecipe(
            source_id="process_regulations",
            collect=(
                "Регламенты работы команды.",
                "Scrum/Kanban гайды.",
                "Правила постановки, исполнения и приемки задач.",
            ),
            systems=(
                "Wiki компании.",
                "Confluence/Notion.",
                "Выгрузка описаний рабочих процессов.",
            ),
            export_hint="Экспортируй страницы как Markdown/HTML/PDF.",
        ),
        "sla_rules": SourceRecipe(
            source_id="sla_rules",
            collect=(
                "SLA по типам задач.",
                "Сроки реакции и выполнения: баг, статья, аналитика, инвойс.",
                "Правила эскалации при просрочке.",
            ),
            systems=(
                "Confluence/Notion.",
                "Jira Service Management SLA.",
                "Team handbook.",
            ),
            export_hint="CSV/XLSX удобнее всего, но подойдет Markdown/PDF.",
        ),
        "task_tracker_rules": SourceRecipe(
            source_id="task_tracker_rules",
            collect=(
                "Правила работы с Jira/Trello.",
                "Как переводить статусы.",
                "Какие теги, labels, priorities и assignees ставить.",
            ),
            systems=(
                "Jira workflow export.",
                "Trello board export JSON.",
                "Confluence описание workflow.",
            ),
            export_hint="Положи Jira/Trello export JSON/CSV или Markdown-описание процесса.",
        ),
        "routing_rules": SourceRecipe(
            source_id="routing_rules",
            collect=(
                "Кому какую задачу отдавать.",
                "Сигналы маршрутизации по ключевым словам и смыслу.",
                "Правила разбиения комплексных задач.",
            ),
            systems=(
                "Матрица компетенций.",
                "Внутренние регламенты.",
                "Список ролей AI Office.",
            ),
            export_hint="CSV/Markdown таблица компетенций будет оптимальна.",
        ),
        "smart_templates": SourceRecipe(
            source_id="smart_templates",
            collect=(
                "Шаблоны постановки задач.",
                "SMART-форматы для разных отделов.",
                "Expected output и acceptance criteria.",
            ),
            systems=(
                "PMO handbook.",
                "Jira/Trello шаблоны задач.",
                "Confluence/Notion templates.",
            ),
            export_hint="Экспортируй шаблоны как Markdown или HTML.",
        ),
    },
    "copywriter": {
        "brandbook_communications": SourceRecipe(
            source_id="brandbook_communications",
            collect=(
                "Brandbook и редполитика.",
                "Правила форматирования.",
                "Стоп-слова, разрешенные формулировки и tone of voice.",
            ),
            systems=(
                "Google Docs отдела маркетинга.",
                "Brandbook PDF.",
                "Notion/Confluence marketing wiki.",
            ),
            export_hint="Google Docs: File -> Download -> .docx/.html/.pdf, затем положить сюда.",
        ),
        "best_human_content": SourceRecipe(
            source_id="best_human_content",
            collect=(
                "30-50 лучших прошлых постов.",
                "Лучшие статьи, email-рассылки и пресс-релизы.",
                "Примеры текстов, которые точно соответствуют стилю компании.",
            ),
            systems=(
                "Google Docs marketing exports.",
                "Корпоративный блог.",
                "Habr, VC.ru или внутренний блог.",
                "История Telegram/LinkedIn постов.",
            ),
            export_hint=(
                "Сохрани посты как CSV/JSON/HTML или скопируй подборку в .md. "
                "Один файл может содержать много постов."
            ),
        ),
        "product_glossary": SourceRecipe(
            source_id="product_glossary",
            collect=(
                "Глоссарий корпоративных терминов.",
                "Названия продуктов, фичей и модулей.",
                "Запрещенные и предпочтительные формулировки.",
            ),
            systems=(
                "Brandbook.",
                "Product marketing docs.",
                "Notion/Confluence glossary.",
            ),
            export_hint="Подойдет CSV с колонками term/definition или Markdown-таблица.",
        ),
        "pr_templates": SourceRecipe(
            source_id="pr_templates",
            collect=(
                "PR-шаблоны.",
                "Шаблоны пресс-релизов, анонсов, email и соцсетей.",
                "Approved boilerplate о компании.",
            ),
            systems=(
                "Google Docs marketing folder.",
                "PR agency docs.",
                "Внутренние templates.",
            ),
            export_hint="Положи .docx, .pdf, .html или .md шаблоны.",
        ),
    },
    "data_analyst": {
        "data_dictionaries": SourceRecipe(
            source_id="data_dictionaries",
            collect=(
                "Data Dictionary: описание всех баз и таблиц.",
                "DDL: таблицы, колонки, типы, связи.",
                "Описание dashboard datasets.",
            ),
            systems=(
                "pg_dump -s для PostgreSQL DDL.",
                "dbt docs или manifest.",
                "Metabase/Tableau text export.",
                "Внутренняя analytics wiki.",
            ),
            export_hint=(
                "Postgres: pg_dump -s \"$DATABASE_URL\" > schema.sql. "
                "dbt: положи manifest.json/catalog.json или экспорт docs."
            ),
        ),
        "kpi_formulas": SourceRecipe(
            source_id="kpi_formulas",
            collect=(
                "Формулы KPI именно вашей компании.",
                "Как считается Retention, LTV, ROI, CAC.",
                "Исключения, фильтры, окна дат и timezone.",
            ),
            systems=(
                "Analytics wiki.",
                "dbt metrics/semantic layer.",
                "Metabase/Tableau dashboard descriptions.",
                "Финмодель или KPI handbook.",
            ),
            export_hint="Лучше Markdown/CSV: metric, formula, source_table, owner, updated_at.",
        ),
        "sql_patterns": SourceRecipe(
            source_id="sql_patterns",
            collect=(
                "Проверенные SQL-запросы.",
                "Правила join, фильтров, timezone и date windows.",
                "Запросы для регулярных отчетов.",
            ),
            systems=(
                "Metabase saved questions.",
                "dbt models.",
                "Analytics repo.",
                "Tableau custom SQL.",
            ),
            export_hint="Положи .sql, .md или JSON/CSV exports saved questions.",
        ),
        "analytics_reports": SourceRecipe(
            source_id="analytics_reports",
            collect=(
                "Примеры успешных отчетов и дашбордов.",
                "Описание бизнес-логики отчетов.",
                "Текстовые выгрузки из BI.",
            ),
            systems=(
                "Metabase.",
                "Tableau.",
                "Looker/Power BI exports.",
                "Analytics docs.",
            ),
            export_hint="Экспортируй PDF/CSV/HTML/Markdown или текстовое описание dashboard.",
        ),
    },
    "developer": {
        "code_style_guides": SourceRecipe(
            source_id="code_style_guides",
            collect=(
                "Coding Standards.",
                "PEP8/Python правила.",
                "ESLint/TypeScript правила и naming conventions.",
            ),
            systems=(
                "README.md и CONTRIBUTING.md из GitHub/GitLab.",
                "ESLint/ruff/prettier config.",
                "Engineering handbook.",
            ),
            export_hint="Скопируй README/CONTRIBUTING/config файлы или положи repo docs сюда.",
        ),
        "architecture_schemes": SourceRecipe(
            source_id="architecture_schemes",
            collect=(
                "Архитектурные схемы backend/frontend.",
                "ADR и описание сервисов.",
                "Границы модулей и интеграций.",
            ),
            systems=(
                "GitHub/GitLab repo docs.",
                "Confluence architecture docs.",
                "Miro/Figma diagrams exported as PDF.",
            ),
            export_hint="PDF/Markdown/DOCX с архитектурой или README из репозитория.",
        ),
        "api_specs": SourceRecipe(
            source_id="api_specs",
            collect=(
                "Swagger/OpenAPI спецификации JSON/YAML.",
                "Список endpoint-ов и schemas.",
                "Контракты интеграций.",
            ),
            systems=(
                "Swagger/OpenAPI endpoint.",
                "GitHub/GitLab repo.",
                "Postman export.",
            ),
            export_hint="Положи openapi.yaml/openapi.json или Postman collection JSON.",
        ),
        "pull_request_history": SourceRecipe(
            source_id="pull_request_history",
            collect=(
                "Примеры удачных Pull Requests.",
                "Правильные review comments.",
                "Решения по архитектурным tradeoff.",
            ),
            systems=(
                "GitHub Pull Requests.",
                "GitLab Merge Requests.",
                "Code review docs.",
            ),
            export_hint="Экспортируй PR title/body/comments в Markdown/JSON/CSV.",
        ),
    },
    "support": {
        "faq": SourceRecipe(
            source_id="faq",
            collect=(
                "Вся база частых вопросов.",
                "Ответы для клиентов и коллег.",
                "Approved wording для типовых ситуаций.",
            ),
            systems=(
                "Zendesk Help Center.",
                "Intercom Articles.",
                "Jira Service Desk knowledge base.",
                "Внутренний Help Center.",
            ),
            export_hint="Экспортируй HTML/CSV/JSON или сохрани статьи Help Center как PDF/HTML.",
        ),
        "successful_tickets": SourceRecipe(
            source_id="successful_tickets",
            collect=(
                "История закрытых тикетов.",
                "Пары: вопрос пользователя -> ответ саппорта.",
                "Причина закрытия и итоговое решение.",
            ),
            systems=(
                "Zendesk ticket export.",
                "Intercom conversation export.",
                "Jira Service Desk CSV.",
            ),
            export_hint="CSV с колонками question/answer/resolution/status подходит лучше всего.",
        ),
        "user_manuals": SourceRecipe(
            source_id="user_manuals",
            collect=(
                "Руководства пользователя.",
                "Инструкции по продукту.",
                "How-to документы.",
            ),
            systems=(
                "Help Center.",
                "Product docs.",
                "Confluence/Notion manuals.",
            ),
            export_hint="HTML/PDF/Markdown/DOCX.",
        ),
        "troubleshooting_guides": SourceRecipe(
            source_id="troubleshooting_guides",
            collect=(
                "Troubleshooting guides: если ошибка X, сделай шаг 1, шаг 2.",
                "Runbooks и деревья диагностики.",
                "Known issues и workaround.",
            ),
            systems=(
                "Support wiki.",
                "Incident runbooks.",
                "Jira Service Desk docs.",
            ),
            export_hint="Markdown/PDF/HTML. Хорошо работают пошаговые списки.",
        ),
        "escalation_rules": SourceRecipe(
            source_id="escalation_rules",
            collect=(
                "Матрица эскалации.",
                "Когда переводить тикет на L2 или человека.",
                "Critical incident thresholds.",
            ),
            systems=(
                "Support handbook.",
                "Zendesk/Jira SLAs.",
                "Incident management docs.",
            ),
            export_hint="CSV/Markdown таблица: condition, severity, owner, SLA.",
        ),
    },
    "strategist": {
        "okrs": SourceRecipe(
            source_id="okrs",
            collect=(
                "OKR на год/квартал.",
                "Стратегические цели.",
                "Приоритеты продукта и бизнеса.",
            ),
            systems=(
                "Notion/Confluence strategy docs.",
                "Investor/board decks.",
                "Leadership planning docs.",
            ),
            export_hint="PDF/PPTX/Markdown.",
        ),
        "roadmaps": SourceRecipe(
            source_id="roadmaps",
            collect=(
                "Долгосрочная стратегия развития продукта.",
                "Roadmap на год.",
                "Milestones, releases, bets, dependencies.",
            ),
            systems=(
                "Productboard/Jira roadmap export.",
                "Notion roadmap.",
                "Internal planning decks.",
            ),
            export_hint="CSV/XLSX/PPTX/PDF/Markdown.",
        ),
        "market_research": SourceRecipe(
            source_id="market_research",
            collect=(
                "Макроэкономические и отраслевые отчеты.",
                "Аналитические статьи отраслевых СМИ.",
                "Market size, trends, risks with dates.",
            ),
            systems=(
                "McKinsey/Gartner reports if you have rights to use them.",
                "Локальные отраслевые ресурсы по нише.",
                "Investor research folder.",
            ),
            export_hint="PDF/HTML/Markdown. Обязательно сохраняй дату источника.",
        ),
        "competitor_dossiers": SourceRecipe(
            source_id="competitor_dossiers",
            collect=(
                "Профили конкурентов.",
                "Фичи, цены, позиционирование.",
                "Ваше преимущество и слабые места конкурентов.",
            ),
            systems=(
                "Сайты конкурентов.",
                "Sales battlecards.",
                "Market research docs.",
            ),
            export_hint="CSV/Markdown таблица competitor/features/pricing/source_date.",
        ),
        "business_plans": SourceRecipe(
            source_id="business_plans",
            collect=(
                "Внутренние презентации для инвесторов.",
                "Прошлые бизнес-планы.",
                "Финмодели и стратегические мемо.",
            ),
            systems=(
                "Investor decks PDF/PPTX.",
                "Google Slides/Docs exports.",
                "Finance planning folder.",
            ),
            export_hint="PPTX/PDF/XLSX/Markdown.",
        ),
    },
    "accountant": {
        "invoice_templates": SourceRecipe(
            source_id="invoice_templates",
            collect=(
                "Шаблоны договоров.",
                "Шаблоны счетов на оплату.",
                "Шаблоны актов выполненных работ.",
            ),
            systems=(
                "Finance/legal templates folder.",
                "1C/ERP document templates.",
                "Internal PDF/DOCX instructions.",
            ),
            export_hint="DOCX/PDF/Markdown. Не клади реальные персональные данные без необходимости.",
        ),
        "accounting_policy": SourceRecipe(
            source_id="accounting_policy",
            collect=(
                "Внутренняя учетная политика.",
                "Правила признания расходов и документов.",
                "Finance closing rules.",
            ),
            systems=(
                "Внутренние PDF-инструкции финансового директора.",
                "1C/ERP регламенты.",
                "Finance wiki.",
            ),
            export_hint="PDF/DOCX/Markdown.",
        ),
        "expense_policy": SourceRecipe(
            source_id="expense_policy",
            collect=(
                "Политика командировок и расходов.",
                "Что можно оплачивать, что нельзя.",
                "Лимиты суточных и правила reimbursement.",
            ),
            systems=(
                "Finance handbook.",
                "CFO PDF instructions.",
                "HR/Travel policy docs.",
            ),
            export_hint="PDF/DOCX/Markdown/CSV.",
        ),
        "legal_entities": SourceRecipe(
            source_id="legal_entities",
            collect=(
                "Реквизиты юрлиц.",
                "БИН, ИИН, расчетные счета, банк.",
                "Юридический адрес и подписанты.",
            ),
            systems=(
                "Finance/legal entity cards.",
                "1C/ERP справочники.",
                "CFO-approved docs.",
            ),
            export_hint="CSV/XLSX/Markdown. Проверь, что это официальная актуальная версия.",
        ),
        "tax_reference": SourceRecipe(
            source_id="tax_reference",
            collect=(
                "Налоговые ставки.",
                "Юрисдикция и effective dates.",
                "Правила НДС/прочих налогов.",
            ),
            systems=(
                "Finance tax reference.",
                "1C/ERP tax settings.",
                "Official internal tax docs.",
            ),
            export_hint="CSV/YAML/Markdown: tax_name, rate, effective_from, source.",
        ),
        "chart_of_accounts": SourceRecipe(
            source_id="chart_of_accounts",
            collect=(
                "План счетов компании.",
                "Коды счетов и правила использования.",
                "Категории операций.",
            ),
            systems=(
                "1C export.",
                "ERP chart of accounts.",
                "Finance handbook.",
            ),
            export_hint="CSV/XLSX/YAML/Markdown.",
        ),
        "approval_matrix": SourceRecipe(
            source_id="approval_matrix",
            collect=(
                "Матрица согласования сумм.",
                "Кто утверждает расходы по категориям и лимитам.",
                "Пороговые суммы и exceptional cases.",
            ),
            systems=(
                "Finance approval policy.",
                "ERP approval workflow.",
                "CFO instructions.",
            ),
            export_hint="CSV/XLSX/Markdown таблица amount/category/approver.",
        ),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse local raw knowledge exports into isolated Markdown folders."
    )
    parser.add_argument(
        "--agent",
        default="all",
        help=(
            "common, pmo, copywriter, developer, support, data_analyst, "
            "accountant, strategist, or all."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Raw input folder or file. Defaults to data/raw_knowledge/<agent>; "
            "for --agent all defaults to data/raw_knowledge/ with agent subfolders."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "knowledge",
        help="Knowledge output root. Defaults to ./knowledge.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Force all parsed files into a specific source id, e.g. brandbook_communications.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without creating Markdown files.",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable simple secret redaction. Use only for trusted internal runs.",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List known source ids and output folders, then exit.",
    )
    parser.add_argument(
        "--source-plan",
        action="store_true",
        help="Print built-in source recipes: what to collect and where to get it.",
    )
    parser.add_argument(
        "--write-source-plan",
        action="store_true",
        help="Write data/raw_knowledge/SOURCE_PLAN.md with built-in source recipes.",
    )
    parser.add_argument(
        "--init-raw",
        action="store_true",
        help="Create data/raw_knowledge folder structure for all parser targets, then exit.",
    )
    parser.add_argument(
        "--seed-local",
        action="store_true",
        help="Copy existing project documents into data/raw_knowledge as bootstrap inputs.",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Run scripts/ingest_knowledge.py after parsing.",
    )
    parser.add_argument(
        "--force-ingest",
        action="store_true",
        help="Run ingest even when no new files were parsed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_catalog()

    if args.list_targets:
        print_targets(catalog)
        return

    if args.source_plan:
        print(render_source_plan(catalog, owners_from_arg(args.agent)).strip())
        return

    if args.write_source_plan:
        write_source_plan(catalog, owners_from_arg(args.agent))
        return

    if args.init_raw:
        init_raw_folders(catalog)
        return

    if args.seed_local:
        seed_local_raw_sources(catalog)
        return

    owners = owners_from_arg(args.agent)
    unknown = [owner for owner in owners if owner not in SOURCE_PROFILES]
    if unknown:
        raise SystemExit(f"Unknown agent/source owner: {', '.join(unknown)}")

    parsed: list[ParsedDocument] = []
    for owner in owners:
        input_path = resolve_input_path(owner=owner, args_input=args.input, all_mode=args.agent == "all")
        if not input_path.exists():
            print(f"[skip] {owner}: missing input path {input_path}")
            continue
        parsed.extend(
            parse_owner_sources(
                owner=owner,
                input_path=input_path,
                output_root=args.output_root,
                catalog=catalog,
                force_source=args.source,
                dry_run=args.dry_run,
                redact=not args.no_redact,
            )
        )

    print_summary(parsed, dry_run=args.dry_run)

    if args.ingest and not args.dry_run:
        if not parsed and not args.force_ingest:
            print()
            print("[skip] ingest was not started because parser found 0 new files.")
            print("       Put exports into data/raw_knowledge/... and run dry-run again.")
            print("       To reindex existing knowledge anyway, add --force-ingest or run:")
            print("       python3 scripts/ingest_knowledge.py --agent all --include-common")
            return
        run_ingest(agent=args.agent)


def load_catalog() -> dict[str, Any]:
    with open(KNOWLEDGE_CATALOG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def print_targets(catalog: dict[str, Any]) -> None:
    for owner in SOURCE_PROFILES:
        print(f"{owner}:")
        for source_id, path in catalog_source_paths(catalog, owner).items():
            print(f"  - {source_id}: {path}")


def owners_from_arg(agent: str) -> list[str]:
    return list(SOURCE_PROFILES) if agent == "all" else [agent]


def resolve_input_path(*, owner: str, args_input: Optional[Path], all_mode: bool) -> Path:
    if args_input is None:
        return DEFAULT_RAW_ROOT / owner

    expanded = args_input.expanduser()
    if all_mode:
        return expanded / owner
    return expanded


def parse_owner_sources(
    *,
    owner: str,
    input_path: Path,
    output_root: Path,
    catalog: dict[str, Any],
    force_source: Optional[str],
    dry_run: bool,
    redact: bool,
) -> list[ParsedDocument]:
    source_paths = catalog_source_paths(catalog, owner)
    validate_forced_source(owner=owner, force_source=force_source, source_paths=source_paths)

    documents: list[ParsedDocument] = []
    source_files = list(iter_source_files(input_path))
    if not source_files:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(f"[skip] {owner}: no supported files found in {input_path}")
        print(f"       supported formats: {supported}")
        return documents

    for path in source_files:
        try:
            body = convert_file_to_markdown(path)
        except Exception as error:
            print(f"[error] {owner}: failed to parse {path}: {error}")
            continue

        if redact:
            body = redact_sensitive_text(body)

        if not body.strip():
            print(f"[skip] {owner}: empty parsed text {path}")
            continue

        source_id = force_source or classify_source(owner, path, input_path, body)
        target_dir = resolve_output_dir(
            source_id=source_id,
            source_paths=source_paths,
            output_root=output_root,
        )
        output_path = target_dir / output_filename(owner, source_id, path, input_path)
        rendered = render_parsed_document(
            owner=owner,
            source_id=source_id,
            input_path=path,
            body=body,
        )

        status = "would_write" if dry_run else "written"
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")

        print(f"[{status}] {path} -> {output_path}")
        documents.append(
            ParsedDocument(
                owner=owner,
                source_id=source_id,
                input_path=path,
                output_path=output_path,
                characters=len(rendered),
                status=status,
            )
        )

    return documents


def catalog_source_paths(catalog: dict[str, Any], owner: str) -> dict[str, str]:
    if owner == "common":
        sources = catalog.get("common", {}).get("sources", [])
    else:
        sources = catalog.get("agents", {}).get(owner, {}).get("sources", [])
    return {source["id"]: source["path"] for source in sources}


def init_raw_folders(catalog: dict[str, Any]) -> None:
    """Create local raw source folders matching configured knowledge targets."""
    created = 0
    for owner in SOURCE_PROFILES:
        for source_id, source_path in catalog_source_paths(catalog, owner).items():
            raw_path = raw_path_for_knowledge_path(owner=owner, knowledge_path=source_path)
            if not raw_path.exists():
                raw_path.mkdir(parents=True, exist_ok=True)
                created += 1
            hint_path = raw_path / SOURCE_HINT_FILENAME
            if not hint_path.exists():
                hint_path.write_text(
                    render_source_hint(
                        owner=owner,
                        source_id=source_id,
                        raw_path=raw_path,
                        knowledge_path=source_path,
                    ),
                    encoding="utf-8",
                )
                created += 1

    readme_path = DEFAULT_RAW_ROOT / "README.md"
    if not readme_path.exists():
        readme_path.write_text(raw_readme(), encoding="utf-8")
        created += 1

    print(f"Raw knowledge folders ready: {DEFAULT_RAW_ROOT}")
    print(f"Created {created} new item(s).")
    print("Put source exports into the matching folders, then run:")
    print("  python3 scripts/parse_knowledge_sources.py --agent all --dry-run")
    print("Source hints are stored in _SOURCE_HINT.md files inside each folder.")


def render_source_hint(
    *,
    owner: str,
    source_id: str,
    raw_path: Path,
    knowledge_path: str,
) -> str:
    recipe = SOURCE_RECIPES.get(owner, {}).get(source_id)
    if not recipe:
        return normalize_markdown(
            f"""# Source Hint: {owner}/{source_id}

Raw folder: `{safe_display_path(raw_path)}`
Output folder: `{knowledge_path}`

No built-in recipe is registered for this source yet.
"""
        )

    lines = [
        f"# Source Hint: {owner}/{source_id}",
        "",
        f"Raw folder: `{safe_display_path(raw_path)}`",
        f"Output folder: `{knowledge_path}`",
        "",
        "## What to collect",
        "",
        *[f"- {item}" for item in recipe.collect],
        "",
        "## Where to get it",
        "",
        *[f"- {item}" for item in recipe.systems],
        "",
        "## Export hint",
        "",
        recipe.export_hint,
        "",
        "## Supported local formats",
        "",
        ", ".join(f"`{extension}`" for extension in sorted(SUPPORTED_EXTENSIONS)),
        "",
        "This hint file is ignored by the parser.",
    ]
    return normalize_markdown("\n".join(lines))


def render_source_plan(catalog: dict[str, Any], owners: list[str]) -> str:
    lines = [
        "# AI Office Source Plan",
        "",
        "This plan is generated from built-in parser recipes.",
        "",
    ]
    for owner in owners:
        source_paths = catalog_source_paths(catalog, owner)
        lines.extend([f"## {owner}", ""])
        for source_id, knowledge_path in source_paths.items():
            recipe = SOURCE_RECIPES.get(owner, {}).get(source_id)
            lines.extend(
                [
                    f"### {source_id}",
                    "",
                    f"- Raw folder: `{safe_display_path(raw_path_for_knowledge_path(owner=owner, knowledge_path=knowledge_path))}`",
                    f"- Output folder: `{knowledge_path}`",
                    "",
                ]
            )
            if not recipe:
                lines.extend(["No built-in recipe registered.", ""])
                continue

            lines.extend(["What to collect:"])
            lines.extend(f"- {item}" for item in recipe.collect)
            lines.extend(["", "Where to get it:"])
            lines.extend(f"- {item}" for item in recipe.systems)
            lines.extend(["", f"Export hint: {recipe.export_hint}", ""])
    return normalize_markdown("\n".join(lines))


def write_source_plan(catalog: dict[str, Any], owners: list[str]) -> None:
    DEFAULT_RAW_ROOT.mkdir(parents=True, exist_ok=True)
    path = DEFAULT_RAW_ROOT / SOURCE_PLAN_FILENAME
    path.write_text(render_source_plan(catalog, owners), encoding="utf-8")
    print(f"Wrote source plan: {path}")


def seed_local_raw_sources(catalog: dict[str, Any]) -> None:
    """Seed raw folders with documents that already exist in this repository."""
    init_raw_folders(catalog)

    seeds = (
        ("AI_Office_business_case.md", "common", "company_overview"),
        ("README.md", "common", "company_overview"),
        ("docs/AGENT_TRAINING_PLAN.md", "common", "ai_office_roles"),
        ("docs/KNOWLEDGE_SOURCE_INTAKE.md", "common", "general_business_processes"),
        ("knowledge/common/tone_of_voice/corporate_tone_of_voice.md", "common", "corporate_tone_of_voice"),
        ("docs/AGENT_TRAINING_PLAN.md", "pmo", "process_regulations"),
        ("config/knowledge_sources.yaml", "pmo", "routing_rules"),
        ("prompts/pmo.yaml", "pmo", "routing_rules"),
        ("knowledge/pmo/sla/pilot_sla.md", "pmo", "sla_rules"),
        ("knowledge/pmo/task_tracker_rules/jira_trello_workflow.md", "pmo", "task_tracker_rules"),
        ("knowledge/pmo/smart_templates/smart_task_templates.md", "pmo", "smart_templates"),
        ("prompts/copywriter.yaml", "copywriter", "brandbook_communications"),
        ("knowledge/copywriter/brandbook/editorial_policy.md", "copywriter", "brandbook_communications"),
        ("AI_Office_business_case.md", "copywriter", "best_human_content"),
        ("knowledge/copywriter/glossary/ai_office_glossary.md", "copywriter", "product_glossary"),
        ("knowledge/copywriter/pr_templates/public_announcement_templates.md", "copywriter", "pr_templates"),
        ("README.md", "developer", "architecture_schemes"),
        ("knowledge/developer/architecture/ai_office_architecture.md", "developer", "architecture_schemes"),
        ("knowledge/developer/api_specs/office_api_openapi.yaml", "developer", "api_specs"),
        ("knowledge/developer/style_guides/python_project_style.md", "developer", "code_style_guides"),
        ("knowledge/developer/pull_requests/review_guidelines.md", "developer", "pull_request_history"),
        ("knowledge/support/faq/ai_office_faq.md", "support", "faq"),
        ("knowledge/support/successful_tickets/route_only_ticket_example.md", "support", "successful_tickets"),
        ("knowledge/support/user_manuals/basic_user_manual.md", "support", "user_manuals"),
        ("knowledge/support/troubleshooting_guides/basic_troubleshooting_tree.md", "support", "troubleshooting_guides"),
        ("knowledge/support/escalation_rules/l1_l2_escalation.md", "support", "escalation_rules"),
        ("knowledge/data_analyst/data_dictionaries/ai_office_data_dictionary.md", "data_analyst", "data_dictionaries"),
        ("knowledge/data_analyst/kpi_formulas/ai_office_kpi_formulas.md", "data_analyst", "kpi_formulas"),
        ("knowledge/data_analyst/sql_patterns/safe_sql_patterns.md", "data_analyst", "sql_patterns"),
        ("knowledge/data_analyst/report_examples/agent_unit_economics_report.md", "data_analyst", "analytics_reports"),
        ("knowledge/strategist/okrs/ai_office_pilot_okrs.md", "strategist", "okrs"),
        ("knowledge/strategist/roadmaps/ai_office_pilot_roadmap.md", "strategist", "roadmaps"),
        ("knowledge/strategist/market_research/market_research_source_requirements.md", "strategist", "market_research"),
        ("knowledge/strategist/competitors/ai_office_positioning.md", "strategist", "competitor_dossiers"),
        ("AI_Office_business_case.md", "strategist", "business_plans"),
        ("knowledge/accountant/document_templates/invoice_act_contract_templates.md", "accountant", "invoice_templates"),
        ("knowledge/accountant/accounting_policy/zero_hallucination_policy.md", "accountant", "accounting_policy"),
        ("knowledge/accountant/expense_policy/expense_policy_requirements.md", "accountant", "expense_policy"),
        ("knowledge/accountant/legal_entities/legal_entities_source_requirements.md", "accountant", "legal_entities"),
        ("knowledge/accountant/tax_reference/tax_source_requirements.md", "accountant", "tax_reference"),
        ("knowledge/accountant/chart_of_accounts/chart_of_accounts_requirements.md", "accountant", "chart_of_accounts"),
        ("knowledge/accountant/approval_matrix/finance_approval_matrix.md", "accountant", "approval_matrix"),
    )

    copied = 0
    skipped = 0
    missing = 0
    for relative_source, owner, source_id in seeds:
        source_path = PROJECT_ROOT / relative_source
        if not source_path.exists():
            print(f"[missing] {relative_source}")
            missing += 1
            continue

        source_paths = catalog_source_paths(catalog, owner)
        knowledge_path = source_paths[source_id]
        target_dir = raw_path_for_knowledge_path(owner=owner, knowledge_path=knowledge_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"local__{source_path.name}"

        if target_path.exists():
            print(f"[skip] {target_path.relative_to(PROJECT_ROOT)}")
            skipped += 1
            continue

        shutil.copy2(source_path, target_path)
        print(f"[seed] {source_path.relative_to(PROJECT_ROOT)} -> {target_path.relative_to(PROJECT_ROOT)}")
        copied += 1

    print()
    print(
        "Local bootstrap seed complete: "
        f"{copied} copied, {skipped} already existed, {missing} missing."
    )
    print("Next:")
    print("  python3 scripts/parse_knowledge_sources.py --agent all --dry-run")


def raw_path_for_knowledge_path(*, owner: str, knowledge_path: str) -> Path:
    configured_path = Path(knowledge_path)
    parts = configured_path.parts
    if len(parts) >= 3 and parts[0] == "knowledge":
        return DEFAULT_RAW_ROOT.joinpath(*parts[1:])
    if len(parts) >= 2:
        return DEFAULT_RAW_ROOT / owner / parts[-1]
    return DEFAULT_RAW_ROOT / owner


def raw_readme() -> str:
    return normalize_markdown(
        """# Raw Knowledge Exports

This folder is for local-only raw exports before parsing.

Put files into the narrowest matching folder, for example:

- `copywriter/brandbook/` for brandbook and editorial policy.
- `copywriter/examples/` for best posts, articles and newsletters.
- `developer/api_specs/` for OpenAPI or Swagger files.
- `data_analyst/data_dictionaries/` for DDL, dbt docs and table descriptions.
- `accountant/legal_entities/` for official legal entity cards.

Each source folder contains `_SOURCE_HINT.md` with a built-in recipe: what to
collect, where to get it, and how to export it.

Then run:

```bash
python3 scripts/parse_knowledge_sources.py --agent all --dry-run
python3 scripts/parse_knowledge_sources.py --agent all --ingest
```

Do not put passwords, API keys or private credentials here.
"""
    )


def validate_forced_source(
    *,
    owner: str,
    force_source: Optional[str],
    source_paths: dict[str, str],
) -> None:
    if force_source and force_source not in source_paths:
        valid = ", ".join(sorted(source_paths))
        raise SystemExit(f"Unknown source id for {owner}: {force_source}. Valid: {valid}")


def iter_source_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path
        return

    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            if candidate.name.startswith((".", "_")):
                continue
            if candidate.name in {"README.md", SOURCE_PLAN_FILENAME}:
                continue
            yield candidate


def classify_source(owner: str, path: Path, input_root: Path, body: str) -> str:
    profiles = SOURCE_PROFILES[owner]
    parts = [part.lower() for part in path.relative_to(input_root).parts[:-1]]
    filename = path.stem.lower()
    path_text = " ".join(parts + [filename]).replace("-", "_")
    body_sample = body[:6000].lower()

    best_source = DEFAULT_SOURCE_BY_OWNER[owner]
    best_score = -1
    for profile in profiles:
        aliases = normalized_terms((profile.source_id,) + profile.aliases)
        keywords = normalized_terms(profile.keywords)
        score = 0

        for part in parts:
            normalized_part = normalize_match_text(part)
            if normalized_part in aliases:
                score += 100

        for alias in aliases:
            if alias and alias in normalize_match_text(path_text):
                score += 30

        for keyword in keywords:
            if keyword in normalize_match_text(path_text):
                score += 12
            if keyword in normalize_match_text(body_sample):
                score += 4

        if score > best_score:
            best_source = profile.source_id
            best_score = score

    return best_source


def normalized_terms(terms: Iterable[str]) -> tuple[str, ...]:
    return tuple(normalize_match_text(term) for term in terms)


def normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("-", "_")).strip()


def resolve_output_dir(
    *,
    source_id: str,
    source_paths: dict[str, str],
    output_root: Path,
) -> Path:
    configured = source_paths[source_id]
    configured_path = Path(configured)
    try:
        relative = configured_path.relative_to("knowledge")
    except ValueError:
        relative = configured_path
    return output_root / relative


def output_filename(owner: str, source_id: str, path: Path, input_root: Path) -> str:
    relative = safe_relative(path, input_root)
    digest_payload = f"{owner}:{source_id}:{relative.as_posix()}"
    digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:10]
    slug = slugify(path.stem)
    return f"{slug}__parsed_{digest}.md"


def safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "-", value.lower()).strip("-_")
    return slug or "source"


def render_parsed_document(
    *,
    owner: str,
    source_id: str,
    input_path: Path,
    body: str,
) -> str:
    title = extract_title(body) or input_path.stem.replace("_", " ").replace("-", " ").strip()
    metadata = [
        f"- Owner: `{owner}`",
        f"- Source id: `{source_id}`",
        f"- Source file: `{safe_display_path(input_path)}`",
        f"- Source format: `{input_path.suffix.lower().lstrip('.') or 'unknown'}`",
        "- Parser: `scripts/parse_knowledge_sources.py`",
    ]

    return normalize_markdown(
        "\n".join(
            [
                f"# {title}",
                "",
                "> Parsed source metadata",
                ">",
                *[f"> {line}" for line in metadata],
                "",
                "---",
                "",
                body.strip(),
                "",
            ]
        )
    )


def safe_display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.expanduser().as_posix()


def extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()
    return ""


def convert_file_to_markdown(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return normalize_markdown(read_text(path))
    if suffix in {".txt"}:
        return text_to_markdown(read_text(path), title=path.stem)
    if suffix in {".yaml", ".yml"}:
        return fenced_block(read_text(path), language="yaml", title=path.stem)
    if suffix == ".sql":
        return fenced_block(read_text(path), language="sql", title=path.stem)
    if suffix == ".json":
        return json_to_markdown(path)
    if suffix == ".jsonl":
        return jsonl_to_markdown(path)
    if suffix == ".csv":
        return csv_to_markdown(path)
    if suffix in {".html", ".htm"}:
        return html_to_markdown(read_text(path))
    if suffix == ".pdf":
        return pdf_to_markdown(path)
    if suffix == ".docx":
        return docx_to_markdown(path)
    if suffix == ".pptx":
        return pptx_to_markdown(path)
    if suffix == ".xlsx":
        return xlsx_to_markdown(path)
    raise ValueError(f"Unsupported file extension: {suffix}")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def text_to_markdown(text: str, *, title: str) -> str:
    return normalize_markdown(f"# {title}\n\n{text}")


def fenced_block(text: str, *, language: str, title: str) -> str:
    return normalize_markdown(f"# {title}\n\n```{language}\n{text.strip()}\n```")


def json_to_markdown(path: Path) -> str:
    data = json.loads(read_text(path))
    title = path.stem.replace("_", " ").replace("-", " ")
    return structured_data_to_markdown(data, title=title, format_name="json")


def jsonl_to_markdown(path: Path) -> str:
    rows: list[Any] = []
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            rows.append({"line": line_number, "parse_error": str(error), "raw": line})
    title = path.stem.replace("_", " ").replace("-", " ")
    return structured_data_to_markdown(rows, title=title, format_name="jsonl")


def structured_data_to_markdown(data: Any, *, title: str, format_name: str) -> str:
    lines = [f"# {title}", ""]
    if isinstance(data, list):
        lines.extend(sequence_to_markdown(data))
    elif isinstance(data, dict):
        lines.extend(mapping_to_markdown(data))
    else:
        lines.extend(["```" + format_name, json.dumps(data, ensure_ascii=False, indent=2), "```"])
    return normalize_markdown("\n".join(lines))


def sequence_to_markdown(rows: list[Any]) -> list[str]:
    lines = [f"Total records: {len(rows)}", ""]
    for index, row in enumerate(rows, start=1):
        lines.append(f"## Record {index}")
        lines.append("")
        if isinstance(row, dict):
            lines.extend(mapping_to_markdown(row, heading_level=3))
        else:
            lines.append(json.dumps(row, ensure_ascii=False, indent=2))
        lines.append("")
    return lines


def mapping_to_markdown(mapping: dict[str, Any], *, heading_level: int = 2) -> list[str]:
    simple_items: list[tuple[str, Any]] = []
    nested_items: list[tuple[str, Any]] = []
    for key, value in mapping.items():
        if isinstance(value, (dict, list)):
            nested_items.append((key, value))
        else:
            simple_items.append((key, value))

    lines: list[str] = []
    for key, value in simple_items:
        lines.append(f"- **{key}:** {format_scalar(value)}")

    for key, value in nested_items:
        lines.extend(["", f"{'#' * heading_level} {key}", ""])
        if isinstance(value, dict):
            lines.extend(mapping_to_markdown(value, heading_level=heading_level + 1))
        else:
            lines.extend(sequence_to_markdown(value))

    return lines


def format_scalar(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    return text


def csv_to_markdown(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(file, dialect=dialect)
        rows = list(reader)

    title = path.stem.replace("_", " ").replace("-", " ")
    if not rows:
        return f"# {title}\n\nNo rows found."

    lines = [f"# {title}", "", f"Total rows: {len(rows)}", ""]
    fieldnames = list(rows[0].keys())
    if len(rows) <= 30 and len(fieldnames) <= 8:
        lines.extend(markdown_table(rows, fieldnames))
        return normalize_markdown("\n".join(lines))

    for index, row in enumerate(rows, start=1):
        lines.extend([f"## Row {index}", ""])
        for key in fieldnames:
            lines.append(f"- **{key}:** {format_scalar(row.get(key, ''))}")
        lines.append("")
    return normalize_markdown("\n".join(lines))


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    lines = [
        "| " + " | ".join(escape_table_cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(escape_table_cell(format_scalar(row.get(column, ""))) for column in columns)
            + " |"
        )
    return lines


def escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


class SimpleMarkdownHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._link_href: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self.parts.append("\n\n" + "#" * level + " ")
        elif tag in {"p", "div", "section", "article", "header", "footer"}:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"ul", "ol"}:
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "tr":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")
        elif tag == "a":
            attrs_dict = dict(attrs)
            self._link_href = attrs_dict.get("href")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"p", "div", "section", "article", "li", "tr"}:
            self.parts.append("\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")
        elif tag == "a":
            if self._link_href:
                self.parts.append(f" ({self._link_href})")
            self._link_href = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.parts.append(text)

    def markdown(self) -> str:
        return normalize_markdown("".join(self.parts))


def html_to_markdown(html_text: str) -> str:
    parser = SimpleMarkdownHTMLParser()
    parser.feed(html_text)
    return parser.markdown()


def pdf_to_markdown(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("pypdf is not installed; install requirements.txt") from error

    reader = PdfReader(str(path))
    lines = [f"# {path.stem}", ""]
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            lines.extend([f"## Page {page_index}", "", text.strip(), ""])
    return normalize_markdown("\n".join(lines))


def docx_to_markdown(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = ElementTree.fromstring(xml_bytes)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines = [f"# {path.stem}", ""]
    for paragraph in root.iter(f"{namespace}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        text = "".join(texts).strip()
        if text:
            lines.extend([text, ""])
    return normalize_markdown("\n".join(lines))


def pptx_to_markdown(path: Path) -> str:
    lines = [f"# {path.stem}", ""]
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide_index, name in enumerate(slide_names, start=1):
            root = ElementTree.fromstring(archive.read(name))
            texts = [
                node.text or ""
                for node in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")
            ]
            text = "\n".join(item.strip() for item in texts if item.strip())
            if text:
                lines.extend([f"## Slide {slide_index}", "", text, ""])
    return normalize_markdown("\n".join(lines))


def xlsx_to_markdown(path: Path) -> str:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is not installed; install requirements.txt") from error

    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except ImportError as error:
        raise RuntimeError("Reading .xlsx requires openpyxl installed locally") from error

    lines = [f"# {path.stem}", ""]
    for sheet_name, frame in sheets.items():
        frame = frame.copy()
        frame.columns = [str(column) for column in frame.columns]
        lines.extend([f"## Sheet: {sheet_name}", "", f"Rows: {len(frame)}", ""])
        rows = frame.fillna("").astype(str).to_dict(orient="records")
        columns = list(frame.columns)
        if len(rows) <= 50 and len(columns) <= 10:
            lines.extend(markdown_table(rows, columns))
            lines.append("")
        else:
            for index, row in enumerate(rows, start=1):
                lines.extend([f"### Row {index}", ""])
                for column in columns:
                    lines.append(f"- **{column}:** {format_scalar(row.get(column, ''))}")
                lines.append("")
    return normalize_markdown("\n".join(lines))


def redact_sensitive_text(text: str) -> str:
    redacted_lines = []
    for line in text.splitlines():
        line = re.sub(
            r"(?i)^(\s*[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET|DATABASE_URL|PRIVATE[_-]?KEY)[A-Z0-9_]*\s*[:=]\s*).+$",
            r"\1[REDACTED]",
            line,
        )
        line = re.sub(
            r"(?i)\b(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1[REDACTED]",
            line,
        )
        line = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", line)
        redacted_lines.append(line)
    return "\n".join(redacted_lines)


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def print_summary(documents: list[ParsedDocument], *, dry_run: bool) -> None:
    verb = "would parse" if dry_run else "parsed"
    print()
    print(f"Summary: {verb} {len(documents)} file(s)")

    counts: dict[tuple[str, str], int] = {}
    for document in documents:
        key = (document.owner, document.source_id)
        counts[key] = counts.get(key, 0) + 1

    for (owner, source_id), count in sorted(counts.items()):
        print(f"- {owner}/{source_id}: {count}")


def run_ingest(*, agent: str) -> None:
    command = [sys.executable, str(PROJECT_ROOT / "scripts" / "ingest_knowledge.py")]
    if agent == "all":
        command.extend(["--agent", "all", "--include-common"])
    elif agent == "common":
        command.extend(["--agent", "all", "--include-common", "--dry-run"])
        print("[info] common-only ingest is not supported directly; run full ingest instead:")
        print("       python3 scripts/ingest_knowledge.py --agent all --include-common")
        return
    else:
        command.extend(["--agent", agent, "--include-common"])

    print()
    print("Running ingest:")
    print(" ".join(command))
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
