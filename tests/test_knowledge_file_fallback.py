import asyncio

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

        async def process_task(self, task, **kwargs):
            self.use_tools = kwargs.get("use_tools")
            return "Ответ модели"

    fake_agent = FakeAgent()
    monkeypatch.setattr(web_app, "get_agent", lambda agent_id: fake_agent)

    result = asyncio.run(web_app.run_agent_text_task("data_analyst", "тест"))

    assert result["task_id"].startswith("web_")
    assert result["result"] == "Ответ модели"
    assert fake_agent.use_tools is False
