from __future__ import annotations

import csv
import textwrap
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "reports" / "ai_office_project_presentation.pdf"

W = 1600
H = 900
BG = "#f5efe5"
PAPER = "#fffaf3"
INK = "#1f2430"
MUTED = "#5e6572"
ACCENT = "#0f766e"
ACCENT_DARK = "#134e4a"
ACCENT_LIGHT = "#d9f0ec"
WARM = "#c26d38"
WARM_LIGHT = "#f7decf"
GOLD = "#d2a44c"
RED = "#b84c3c"
BLUE = "#dfe8fb"
GREEN = "#e6f3ea"
AMBER = "#fff1da"
ROSE = "#fae5e3"

MARGIN = 64


@dataclass
class CostPeriod:
    name: str
    total_usd: Decimal
    nonzero_days: int
    total_days: int


def font_paths() -> tuple[str, str]:
    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    return regular, bold


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    regular, bold_path = font_paths()
    path = bold_path if bold else regular
    return ImageFont.truetype(path, size=size)


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as file:
        return sum(1 for _ in file)


def project_metrics() -> dict[str, int]:
    excluded = {".git", ".venv", ".pytest_cache", ".vercel"}
    py_files: list[Path] = []
    md_files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.parts):
            continue
        if path.suffix == ".py":
            py_files.append(path)
        if path.suffix == ".md":
            md_files.append(path)

    knowledge_md = list((PROJECT_ROOT / "knowledge").rglob("*.md"))
    test_files = list((PROJECT_ROOT / "tests").glob("test_*.py"))
    return {
        "py_files": len(py_files),
        "py_loc": sum(count_lines(path) for path in py_files),
        "md_files": len(md_files),
        "knowledge_md": len(knowledge_md),
        "test_files": len(test_files),
    }


def parse_cost_csv(path: Path) -> CostPeriod | None:
    if not path.exists():
        return None
    total = Decimal("0")
    nonzero_days = 0
    total_days = 0
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            total_days += 1
            raw = str(row.get("amount_value") or "").strip()
            if not raw:
                continue
            value = Decimal(raw)
            total += value
            if value > 0:
                nonzero_days += 1
    return CostPeriod(
        name=path.name.replace("cost_", "").replace(".csv", ""),
        total_usd=total,
        nonzero_days=nonzero_days,
        total_days=total_days,
    )


def rounded_usd(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'))}"


def new_slide(page_number: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.ellipse((W - 340, -40, W - 40, 260), fill=ACCENT_LIGHT)
    draw.ellipse((-40, H - 210, 220, H + 40), fill=WARM_LIGHT)
    draw.rounded_rectangle((MARGIN - 10, MARGIN - 6, W - MARGIN + 10, H - MARGIN + 6), radius=28, fill=PAPER, outline="#ebdfce", width=2)
    draw.text((W - MARGIN - 240, H - 34), f"AI Office • Project Analysis • {page_number}", font=load_font(18), fill=MUTED)
    return img, draw


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int = 24, bold: bool = False, fill: str = INK) -> None:
    draw.text(xy, value, font=load_font(size, bold=bold), fill=fill)


def wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    width: int,
    size: int = 28,
    bold: bool = False,
    fill: str = INK,
    line_gap: int = 10,
) -> int:
    font = load_font(size, bold=bold)
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += size + line_gap
    return y


def bullets(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    items: list[str],
    width: int,
    size: int = 24,
    fill: str = INK,
) -> int:
    x, y = xy
    for item in items:
        draw.ellipse((x, y + 10, x + 10, y + 20), fill=ACCENT)
        y = wrapped_text(draw, (x + 22, y), item, width - 22, size=size, fill=fill, line_gap=8) + 10
    return y


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = "#ffffff", outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline or "#e8dfd0", width=2)


def stat_box(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, accent: str) -> None:
    card(draw, (x, y, x + 220, y + 132))
    draw.rounded_rectangle((x + 18, y + 18, x + 78, y + 42), radius=12, fill=accent)
    text(draw, (x + 18, y + 58), value, size=34, bold=True)
    text(draw, (x + 18, y + 98), label, size=18, fill=MUTED)


def slide_cover(metrics: dict[str, int]) -> Image.Image:
    img, draw = new_slide(1)
    draw.rounded_rectangle((MARGIN, 112, MARGIN + 220, 154), radius=18, fill=ACCENT_DARK)
    text(draw, (MARGIN + 20, 120), "TECHNICAL REVIEW", size=20, bold=True, fill="#ffffff")
    text(draw, (MARGIN, 196), "AI Office", size=58, bold=True)
    text(draw, (MARGIN, 264), "Подробный анализ проекта", size=48, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 340), "Архитектура, зрелость кода, риски, экономика и рекомендации.", 620, size=26, fill=MUTED)
    text(draw, (MARGIN, 420), "Что внутри:", size=28, bold=True)
    bullets(
        draw,
        (MARGIN, 468),
        [
            "мультиагентная архитектура на LangGraph и FastAPI",
            "7 специализированных ролей с доменной изоляцией знаний",
            "RAG, long-term memory, web/API/Telegram контуры",
            "сильные стороны, риски, стоимость и roadmap",
        ],
        620,
        size=24,
    )
    card(draw, (920, 170, 1450, 560))
    text(draw, (960, 210), "Снимок репозитория", size=30, bold=True, fill=ACCENT_DARK)
    stat_box(draw, 960, 278, "Python files", str(metrics["py_files"]), ACCENT)
    stat_box(draw, 1190, 278, "Lines of code", str(metrics["py_loc"]), GOLD)
    stat_box(draw, 960, 424, "Knowledge docs", str(metrics["knowledge_md"]), WARM)
    stat_box(draw, 1190, 424, "Test files", str(metrics["test_files"]), RED)
    return img


def slide_summary(costs: list[CostPeriod]) -> Image.Image:
    img, draw = new_slide(2)
    text(draw, (MARGIN, 86), "Executive Summary", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Коротко: проект уже выглядит как сильный MVP платформы AI-офиса.", 1000, size=24, fill=MUTED)
    card(draw, (MARGIN, 210, 760, 680), fill="#ffffff")
    text(draw, (MARGIN + 26, 240), "Сильные стороны", size=30, bold=True, fill=ACCENT_DARK)
    bullets(draw, (MARGIN + 26, 292), [
        "Чёткая специализация агентов: PMO, аналитика, разработка, копирайтинг, support, strategy, accounting.",
        "Есть изоляция knowledge namespace и локальная long-term memory по ролям.",
        "Поддерживаются несколько каналов доступа: FastAPI, web-чат и Telegram webhook/topic routing.",
        "Тестовый слой живой: локально проходит 36 тестов.",
    ], 650, size=22)
    card(draw, (800, 210, 1450, 680), fill="#fffdf9")
    text(draw, (826, 240), "Главные зазоры", size=30, bold=True, fill=WARM)
    bullets(draw, (826, 292), [
        "README и docstring'и обещают mixed-model stack, но текущий router фактически опирается на OpenAI-пулы.",
        "PMO routing пока эвристический, по keyword map.",
        "PgVector и Pinecone backend'ы пока оставлены как TODO-заглушки.",
        "Support-эскалация использует hardcoded confidence и не отражает реальную уверенность модели.",
    ], 590, size=22)
    if costs:
        text(draw, (MARGIN, 714), "Наблюдаемая стоимость по CSV:", size=20, bold=True, fill=MUTED)
        wrapped_text(draw, (MARGIN + 310, 714), " • ".join(f"{cost.name}: {rounded_usd(cost.total_usd)}" for cost in costs), 820, size=20, fill=MUTED)
    return img


def slide_architecture() -> Image.Image:
    img, draw = new_slide(3)
    text(draw, (MARGIN, 86), "Архитектура", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Проект собран как оркеструемый AI-backend с несколькими каналами доступа.", 980, size=24, fill=MUTED)
    draw.rounded_rectangle((660, 190, 940, 258), radius=18, fill=ACCENT_DARK)
    text(draw, (752, 208), "User / CEO", size=28, bold=True, fill="#ffffff")
    draw.rounded_rectangle((650, 300, 950, 380), radius=18, fill=GOLD)
    text(draw, (735, 325), "PMO Agent", size=34, bold=True)
    draw.line((800, 258, 800, 300), fill=ACCENT_DARK, width=5)
    draw.line((260, 470, 1340, 470), fill=ACCENT_DARK, width=5)
    draw.line((800, 380, 800, 470), fill=ACCENT_DARK, width=5)
    agent_names = ["Data Analyst", "Developer", "Copywriter", "Support", "Strategist", "Accountant"]
    x_positions = [170, 390, 610, 830, 1050, 1270]
    for name, x in zip(agent_names, x_positions):
        draw.line((x, 470, x, 540), fill=ACCENT_DARK, width=4)
        card(draw, (x - 80, 540, x + 80, 608))
        text(draw, (x - 60, 564), name, size=20, bold=True)
    card(draw, (120, 650, 460, 790), fill=ACCENT_LIGHT)
    text(draw, (146, 682), "Контекст и знания", size=28, bold=True, fill=ACCENT_DARK)
    bullets(draw, (146, 724), ["Retriever + namespace isolation", "knowledge/ по ролям", "long-term memory JSONL"], 280, size=20)
    card(draw, (530, 650, 870, 790), fill=BLUE)
    text(draw, (556, 682), "Интерфейсы", size=28, bold=True, fill=ACCENT_DARK)
    bullets(draw, (556, 724), ["FastAPI product API", "web chat + conversations", "Telegram webhooks и topics"], 280, size=20)
    card(draw, (940, 650, 1280, 790), fill=GREEN)
    text(draw, (966, 682), "Интеграции", size=28, bold=True, fill=ACCENT_DARK)
    bullets(draw, (966, 724), ["Slack", "Jira", "GitHub", "ERP/PDF parsing"], 280, size=20)
    return img


def slide_agents() -> Image.Image:
    img, draw = new_slide(4)
    text(draw, (MARGIN, 86), "Ролевой слой", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Каждый агент упакован как отдельный класс со своим prompt, tools и RAG-профилем.", 1100, size=24, fill=MUTED)
    cards = [
        ("PMO", "Входная точка, маршрутизация и декомпозиция задач", ACCENT_LIGHT),
        ("Data Analyst", "SQL, метрики, self-verification и отказ от выдуманных чисел", GREEN),
        ("Developer", "Код, ревью, архитектура и GitHub-инструменты", BLUE),
        ("Copywriter", "Посты, email, PR и бренд-коммуникация", AMBER),
        ("Support", "L1/L2, FAQ, troubleshooting и Telegram workflows", ROSE),
        ("Strategist", "OKR, рынок, roadmaps, business case", "#ece4f8"),
        ("Accountant", "Invoice parsing, tax docs, zero-hallucination policy", "#ddf1ee"),
    ]
    positions = [(80, 220), (560, 220), (1040, 220), (80, 430), (560, 430), (1040, 430), (320, 640)]
    for (name, desc, fill), (x, y) in zip(cards, positions):
        card(draw, (x, y, x + 380, y + 150), fill=fill)
        text(draw, (x + 24, y + 24), name, size=28, bold=True)
        wrapped_text(draw, (x + 24, y + 72), desc, 330, size=22, fill=MUTED)
    return img


def slide_rag() -> Image.Image:
    img, draw = new_slide(5)
    text(draw, (MARGIN, 86), "RAG и Knowledge Pipeline", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Одна из самых сильных частей проекта: явная knowledge-изоляция по ролям.", 1050, size=24, fill=MUTED)
    card(draw, (70, 220, 760, 670))
    text(draw, (96, 248), "Как это устроено", size=30, bold=True, fill=ACCENT_DARK)
    bullets(draw, (96, 302), [
        "`parse_knowledge_sources.py` нормализует сырые выгрузки и редактирует чувствительные данные.",
        "`ingest_knowledge.py` режет документы на чанки и индексирует их в выбранный backend.",
        "`Retriever` навешивает allow-list namespace и `agent_id`, чтобы агент не видел чужую базу знаний.",
        "При отсутствии production vector DB доступен `local_json` backend для smoke/dev сценариев.",
    ], 620, size=22)
    card(draw, (820, 220, 1460, 670), fill="#fffdf9")
    text(draw, (846, 248), "Почему это важно", size=30, bold=True, fill=WARM)
    bullets(draw, (846, 302), [
        "Это сильный фундамент для enterprise-use case с разграничением ролей.",
        "Есть fallback через committed knowledge files, поэтому часть сценариев тестируется без внешней БД.",
        "Ограничение: реальные `pgvector` и `pinecone` адаптеры пока не завершены.",
    ], 560, size=22)
    steps = ["Raw exports", "Parsed markdown", "Chunking", "Vector store", "Scoped retrieval", "Prompt context"]
    x = 90
    for i, step in enumerate(steps):
        card(draw, (x, 730, x + 210, 794), fill="#ffffff")
        wrapped_text(draw, (x + 18, 748), step, 172, size=20, bold=True)
        if i < len(steps) - 1:
            draw.line((x + 210, 762, x + 248, 762), fill=ACCENT_DARK, width=4)
        x += 248
    return img


def slide_interfaces() -> Image.Image:
    img, draw = new_slide(6)
    text(draw, (MARGIN, 86), "Каналы взаимодействия", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Проект уже выглядит как backend-платформа, а не только как набор agent-классов.", 1100, size=24, fill=MUTED)
    columns = [
        ("API", ["`/api/office/tasks` для продового вызова", "`/api/office/routes` для route inspection", "RAG hit metadata и Telegram notify flag"], 80),
        ("Web", ["FastAPI + Jinja templates", "conversation storage и chat history", "PMO dispatch и direct specialist chat"], 560),
        ("Telegram", ["Webhook для общего PMO и specialist topics", "Команды `/agent` и `/bind`", "Ответы агентами в нужную ветку"], 1040),
    ]
    for heading, items, x in columns:
        card(draw, (x, 230, x + 380, 650))
        text(draw, (x + 24, 260), heading, size=30, bold=True, fill=ACCENT_DARK)
        bullets(draw, (x + 24, 318), items, 330, size=22)
    card(draw, (80, 700, 1420, 804), fill="#f1f6ff")
    text(draw, (110, 728), "Практический вывод", size=26, bold=True)
    bullets(draw, (110, 766), [
        "Система уже готова к нескольким точкам входа: web, bot и внешний продуктовый API.",
        "Это повышает ценность проекта как платформы для AI Operations, а не только как демо одного use case.",
    ], 1260, size=21)
    return img


def slide_quality() -> Image.Image:
    img, draw = new_slide(7)
    text(draw, (MARGIN, 86), "Качество и надёжность", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "У проекта есть хорошие инженерные привычки, хотя часть логики пока MVP-уровня.", 1100, size=24, fill=MUTED)
    card(draw, (80, 230, 520, 650), fill=GREEN)
    text(draw, (106, 258), "Плюсы", size=30, bold=True, fill=ACCENT_DARK)
    bullets(draw, (106, 314), [
        "36 тестов проходят локально.",
        "Проверяются memory pruning, namespace policies, API и Telegram workflows.",
        "Есть обработка пустого ответа модели и graceful fallback для offline сценариев.",
    ], 370, size=22)
    card(draw, (560, 230, 970, 650), fill=AMBER)
    text(draw, (586, 258), "MVP-компромиссы", size=30, bold=True, fill=WARM)
    bullets(draw, (586, 314), [
        "keyword-routing в PMO",
        "stub backend'ы для production vector DB",
        "часть docstring'ов уже расходится с кодом",
    ], 360, size=22)
    card(draw, (1010, 230, 1420, 650), fill=ROSE)
    text(draw, (1036, 258), "Главный риск", size=30, bold=True, fill=RED)
    bullets(draw, (1036, 314), [
        "Разрыв между позиционированием и фактической реализацией может вводить в заблуждение команду и пользователей.",
        "Перед внешней демонстрацией стоит синхронизировать README, конфиг и рабочие providers.",
    ], 360, size=22)
    draw.rounded_rectangle((80, 714, 760, 770), radius=18, fill="#ffffff", outline="#e8dfd0", width=2)
    text(draw, (104, 730), "Local check: python3 -m pytest -q  ->  36 passed in 2.80s", size=22, fill=MUTED)
    return img


def slide_costs(costs: list[CostPeriod]) -> Image.Image:
    img, draw = new_slide(8)
    text(draw, (MARGIN, 86), "Экономика модели", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Даже по небольшим CSV видно, зачем проекту нужен model routing и лёгкие fallback-пути.", 1100, size=24, fill=MUTED)
    card(draw, (80, 230, 760, 650))
    text(draw, (106, 258), "Что видно по расходам", size=30, bold=True, fill=ACCENT_DARK)
    if costs:
        bullets(draw, (106, 316), [
            f"{costs[0].name}: {rounded_usd(costs[0].total_usd)} за {costs[0].nonzero_days} активных дней из {costs[0].total_days}.",
            f"{costs[1].name}: {rounded_usd(costs[1].total_usd)} за {costs[1].nonzero_days} активных дней из {costs[1].total_days}." if len(costs) > 1 else "Доступен один период стоимости.",
            "При росте числа задач стоимость будет расти, если не разводить простые и тяжёлые сценарии по моделям.",
            "В проекте уже заложена полезная идея `default/heavy` для контроля себестоимости.",
        ], 620, size=22)
    card(draw, (820, 230, 1420, 650), fill="#fffdf9")
    text(draw, (846, 258), "Сравнение периодов", size=30, bold=True, fill=WARM)
    if costs:
        max_total = max(float(cost.total_usd) for cost in costs) or 1.0
        bar_x = 960
        colors = [ACCENT, WARM]
        for i, cost in enumerate(costs):
            x = bar_x + i * 200
            bar_h = int(250 * float(cost.total_usd) / max_total)
            draw.rounded_rectangle((x, 560 - bar_h, x + 90, 560), radius=16, fill=colors[i % len(colors)])
            text(draw, (x - 6, 570), cost.name, size=16, fill=MUTED)
            text(draw, (x, 520 - bar_h), rounded_usd(cost.total_usd), size=20, bold=True)
    wrapped_text(draw, (80, 714), "Источник: локальные файлы cost_2026-04-01_2026-05-01.csv и cost_2026-05-02_2026-05-13.csv.", 1180, size=20, fill=MUTED)
    return img


def slide_risks() -> Image.Image:
    img, draw = new_slide(9)
    text(draw, (MARGIN, 86), "Риски и несоответствия", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Именно эти точки сильнее всего влияют на путь от MVP к production.", 1050, size=24, fill=MUTED)
    risk_cards = [
        ("1. Документация vs код", "README обещает Claude/Gemini mix, но в текущем роутере активные пулы настроены на OpenAI.", ROSE, RED),
        ("2. Routing maturity", "PMO использует keyword map, а не полноценную композицию подзадач через planner или structured LLM route.", AMBER, WARM),
        ("3. Vector backends", "`PgVectorStore` и `PineconeStore` логируют действия, но пока не делают реальный поиск.", "#f7eed8", GOLD),
        ("4. Support escalation", "Confidence в support hardcoded, поэтому L2-эскалация пока не отражает реальную уверенность модели.", ACCENT_LIGHT, ACCENT),
    ]
    positions = [(80, 240), (830, 240), (80, 480), (830, 480)]
    for (title_value, body, fill, accent), (x, y) in zip(risk_cards, positions):
        card(draw, (x, y, x + 670, y + 180), fill=fill)
        draw.rounded_rectangle((x + 20, y + 20, x + 260, y + 54), radius=14, fill=accent)
        text(draw, (x + 34, y + 26), title_value, size=18, bold=True, fill="#ffffff")
        wrapped_text(draw, (x + 24, y + 82), body, 620, size=24)
    return img


def slide_roadmap() -> Image.Image:
    img, draw = new_slide(10)
    text(draw, (MARGIN, 86), "Рекомендованный roadmap", size=42, bold=True, fill=ACCENT_DARK)
    wrapped_text(draw, (MARGIN, 138), "Самый рациональный путь: сначала синхронизировать обещания и реализацию, потом усиливать production-ready слой.", 1180, size=24, fill=MUTED)
    phases = [
        ("Sprint 1", "Синхронизировать README, prompts, router и settings.yaml с фактическими моделями и ролями.", ACCENT),
        ("Sprint 2", "Довести production vector backend: embeddings, real search, metadata filters и smoke against pgvector.", GOLD),
        ("Sprint 3", "Заменить keyword-routing на planner-подход со structured route output и confidence.", WARM),
        ("Sprint 4", "Добавить observability: latency, cost per agent, escalation rate, retrieval hit-rate.", RED),
        ("Sprint 5", "Подготовить бизнес-демо на реальных пользовательских сценариях и KPI по отделам.", ACCENT_DARK),
    ]
    y = 240
    for phase, desc, color in phases:
        draw.ellipse((110, y + 6, 146, y + 42), fill=color)
        draw.line((128, y + 42, 128, y + 94), fill="#d6cebf", width=5)
        text(draw, (176, y), phase, size=28, bold=True)
        wrapped_text(draw, (356, y), desc, 980, size=24)
        y += 118
    return img


def slide_closing() -> Image.Image:
    img, draw = new_slide(11)
    draw.rounded_rectangle((120, 250, 1480, 540), radius=36, fill=ACCENT_DARK)
    text(draw, (180, 328), "AI Office уже выглядит", size=54, bold=True, fill="#ffffff")
    text(draw, (180, 398), "как серьёзная платформа, а не игрушечный прототип.", size=40, bold=True, fill="#ffffff")
    wrapped_text(draw, (180, 468), "Следующий шаг — укрепить production-слой и убрать расхождение между архитектурной идеей и текущей реализацией.", 1120, size=26, fill="#e8f5f2")
    wrapped_text(draw, (120, 620), "Презентация сгенерирована автоматически из структуры проекта, ключевых исходников и локальных cost CSV.", 1120, size=22, fill=MUTED)
    return img


def build_presentation() -> Path:
    metrics = project_metrics()
    cost_paths = [
        Path("/Users/nuras/Downloads/cost_2026-04-01_2026-05-01.csv"),
        Path("/Users/nuras/Downloads/cost_2026-05-02_2026-05-13.csv"),
    ]
    costs = [item for path in cost_paths if (item := parse_cost_csv(path))]

    slides = [
        slide_cover(metrics),
        slide_summary(costs),
        slide_architecture(),
        slide_agents(),
        slide_rag(),
        slide_interfaces(),
        slide_quality(),
        slide_costs(costs),
        slide_risks(),
        slide_roadmap(),
        slide_closing(),
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rgb_slides = [slide.convert("RGB") for slide in slides]
    rgb_slides[0].save(
        OUTPUT_PATH,
        save_all=True,
        append_images=rgb_slides[1:],
        resolution=150.0,
    )
    return OUTPUT_PATH


if __name__ == "__main__":
    print(build_presentation())
