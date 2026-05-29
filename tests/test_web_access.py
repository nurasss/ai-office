from __future__ import annotations

import pytest

from core.config import get_settings
from tools.external import web_tools
from tools.external.web_tools import (
    WebAccessError,
    build_web_context,
    fetch_public_url,
    search_public_web,
    should_use_web_context,
)


def test_web_context_heuristic_only_for_current_tasks():
    assert should_use_web_context("latest OpenAI API docs")
    assert should_use_web_context("актуальные новости рынка")
    assert not should_use_web_context("напиши внутренний план задач")


@pytest.mark.asyncio
async def test_fetch_public_url_blocks_private_hosts(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(WebAccessError):
        await fetch_public_url("http://127.0.0.1:8000/health")

    with pytest.raises(WebAccessError):
        await fetch_public_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_search_public_web_parses_results(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "true")
    get_settings.cache_clear()

    html = """
    <html>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example Docs</a>
      <div class="result__snippet">Useful current documentation.</div>
    </html>
    """

    monkeypatch.setattr(web_tools, "_read_url", lambda *args, **kwargs: html)
    monkeypatch.setattr(web_tools, "_is_safe_public_url", lambda url: True)

    results = await search_public_web("latest docs", max_results=3)

    assert results == [
        {
            "title": "Example Docs",
            "url": "https://example.com/docs",
            "snippet": "Useful current documentation.",
        }
    ]


@pytest.mark.asyncio
async def test_search_public_web_uses_brave_when_configured(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    get_settings.cache_clear()

    payload = {
        "web": {
            "results": [
                {
                    "title": "Market News",
                    "url": "https://example.com/market",
                    "description": "Fresh market update.",
                }
            ]
        }
    }

    monkeypatch.setattr(web_tools, "_is_safe_public_url", lambda url: True)
    monkeypatch.setattr(web_tools.asyncio, "to_thread", lambda func: web_tools.asyncio.sleep(0, result='{"web":{"results":[{"title":"Market News","url":"https://example.com/market","description":"Fresh market update."}]}}'))

    results = await search_public_web("market news", max_results=3)

    assert results == [
        {
            "title": "Market News",
            "url": "https://example.com/market",
            "snippet": "Fresh market update.",
        }
    ]


@pytest.mark.asyncio
async def test_build_web_context_uses_search_for_latest_tasks(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "true")
    get_settings.cache_clear()

    async def fake_search(query: str, *, max_results: int | None = None):
        return [
            {
                "title": "Release Notes",
                "url": "https://example.com/releases",
                "snippet": "Latest release details.",
            }
        ]

    monkeypatch.setattr(web_tools, "search_public_web", fake_search)

    context = await build_web_context("latest release notes")

    assert "Актуальный публичный web-контекст" in context
    assert "https://example.com/releases" in context


@pytest.mark.asyncio
async def test_build_web_context_reports_empty_search_without_claiming_no_access(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "true")
    get_settings.cache_clear()

    async def fake_search(query: str, *, max_results: int | None = None):
        return []

    monkeypatch.setattr(web_tools, "search_public_web", fake_search)

    context = await build_web_context("актуальные новости IT")

    assert "поиск был выполнен" in context
    assert "нет доступа к интернету" in context


@pytest.mark.asyncio
async def test_web_access_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_WEB_ACCESS_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(WebAccessError):
        await search_public_web("latest docs")
