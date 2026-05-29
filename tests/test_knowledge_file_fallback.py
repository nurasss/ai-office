import asyncio

from agents.base.base_agent import BaseAgent
from core.db import get_session, init_db, reset_db_engine
from rag.knowledge_files import format_knowledge_file_context, search_knowledge_files
from services.task_service import TaskService
from web import app as web_app


def test_search_knowledge_files_finds_committed_sales_report():
    hits = search_knowledge_files(
        "data_analyst",
        "годовой отчет продаж самый прибыльный месяц декабрь праздничный сезон",
        top_k=5,
    )

    assert any("годовой-отчет" in hit.source for hit in hits)
    context = format_knowledge_file_context(hits)
    assert "Декабрь" in context
    assert "176  000" in context


def test_web_agent_runner_forces_plain_text_model(monkeypatch, tmp_path):
    class FakeAgent:
        use_tools = None
        max_tokens = None

        async def process_task(self, task, **kwargs):
            self.use_tools = kwargs.get("use_tools")
            self.max_tokens = kwargs.get("max_tokens")
            return "Ответ модели"

    fake_agent = FakeAgent()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plain_text.db'}")
    web_app.get_settings.cache_clear()
    reset_db_engine()
    monkeypatch.setattr(web_app, "get_agent", lambda agent_id: fake_agent)

    result = asyncio.run(web_app.run_agent_text_task("data_analyst", "тест"))

    assert result["task_id"].startswith("web_")
    assert result["result"] == "Ответ модели"
    assert fake_agent.use_tools is False
    assert fake_agent.max_tokens == 2400
    web_app.get_settings.cache_clear()
    reset_db_engine()


def test_web_agent_runner_persists_runtime_task(monkeypatch, tmp_path):
    class FakeAgent:
        async def process_task(self, task, **kwargs):
            return "Готовый результат"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'runtime.db'}")
    web_app.get_settings.cache_clear()
    reset_db_engine()
    init_db()
    monkeypatch.setattr(web_app, "get_agent", lambda agent_id: FakeAgent())

    result = asyncio.run(web_app.run_agent_text_task("strategist", "изучи рынок"))

    assert result["task_id"].startswith("web_")
    with get_session() as db:
        tasks = TaskService(db).list_tasks()
        assert len(tasks) == 1
        assert tasks[0].assigned_agent == "strategist"
        assert tasks[0].status == "completed"
        assert tasks[0].result_summary == "Готовый результат"

    reset_db_engine()
    web_app.get_settings.cache_clear()


def test_rag_context_reads_full_committed_knowledge_source():
    context = BaseAgent._format_rag_context(
        [
            {
                "content": "Январь 450 120 54 000",
                "metadata": {
                    "source": (
                        "knowledge/data_analyst/report_examples/"
                        "годовой-отчет-о-продажах_-тестовая-симуляция-v2__parsed_bc173960d9.md"
                    ),
                    "namespace": "agent_data_analyst",
                    "agent_id": "data_analyst",
                },
            }
        ]
    )

    assert "Декабрь" in context
    assert "176  000" in context
