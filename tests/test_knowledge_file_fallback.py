import asyncio

from agents.base.base_agent import BaseAgent
from rag.knowledge_files import format_knowledge_file_context, search_knowledge_files
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


def test_web_agent_runner_forces_plain_text_model(monkeypatch):
    class FakeAgent:
        use_tools = None
        max_tokens = None

        async def process_task(self, task, **kwargs):
            self.use_tools = kwargs.get("use_tools")
            self.max_tokens = kwargs.get("max_tokens")
            return "Ответ модели"

    fake_agent = FakeAgent()
    monkeypatch.setattr(web_app, "get_agent", lambda agent_id: fake_agent)

    result = asyncio.run(web_app.run_agent_text_task("data_analyst", "тест"))

    assert result["task_id"].startswith("web_")
    assert result["result"] == "Ответ модели"
    assert fake_agent.use_tools is False
    assert fake_agent.max_tokens == 2400


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
