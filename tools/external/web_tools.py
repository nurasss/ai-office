"""Read-only public web tools for current information."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from langchain_core.tools import tool

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("tools.web")

SEARCH_URL = "https://duckduckgo.com/html/"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "AI-Office/1.0 read-only research"
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class WebAccessError(RuntimeError):
    """Raised when a web read is blocked or fails safely."""


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        class_name = attr.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._current = {"title": "", "url": _decode_duckduckgo_url(attr.get("href", "")), "snippet": ""}
            self._capture_title = True
            self._text_parts = []
        elif self._current is not None and "result__snippet" in class_name:
            self._capture_snippet = True
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_title or self._capture_snippet:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_title and tag == "a" and self._current is not None:
            self._current["title"] = _clean_text(" ".join(self._text_parts))
            self._capture_title = False
            self._text_parts = []
            if self._current["title"] and self._current["url"]:
                self.results.append(self._current)
            return
        if self._capture_snippet and tag in {"a", "div"} and self._current is not None:
            self._current["snippet"] = _clean_text(" ".join(self._text_parts))
            self._capture_snippet = False
            self._text_parts = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = _clean_text(data)
            if text:
                self.parts.append(text)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _decode_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query:
        return query["uddg"][0]
    return urllib.parse.urljoin("https://duckduckgo.com", url)


def _read_url(url: str, *, max_bytes: int = 800_000, timeout: int = 10) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if content_type and not any(kind in content_type for kind in ("text/", "html", "json", "xml")):
            raise WebAccessError(f"Unsupported content type: {content_type}")
        raw = response.read(max_bytes)
    return raw.decode("utf-8", errors="replace")


def _is_safe_public_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in BLOCKED_HOSTS or host.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        pass

    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            address = sockaddr[0]
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except OSError:
        return False
    return True


def _ensure_web_enabled() -> None:
    if not get_settings().ai_office_web_access_enabled:
        raise WebAccessError("Public web access is disabled by AI_OFFICE_WEB_ACCESS_ENABLED.")


async def search_public_web(query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
    """Search the public web through a read-only HTML endpoint."""
    _ensure_web_enabled()
    settings = get_settings()
    limit = max(1, min(max_results or settings.ai_office_web_search_max_results, 8))
    query = _clean_text(query)
    if not query:
        return []

    brave_results = await _search_brave(query, limit=limit)
    if brave_results:
        return brave_results

    search_url = f"{SEARCH_URL}?{urllib.parse.urlencode({'q': query})}"
    try:
        html_text = await asyncio.to_thread(_read_url, search_url)
    except Exception as error:
        logger.warning("web.search.failed", error=str(error))
        return []

    parser = SearchResultParser()
    parser.feed(html_text)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in parser.results:
        url = result.get("url", "")
        if not url or url in seen or not _is_safe_public_url(url):
            continue
        seen.add(url)
        results.append(result)
        if len(results) >= limit:
            break
    return results


async def _search_brave(query: str, *, limit: int) -> list[dict[str, str]]:
    """Search through Brave when BRAVE_SEARCH_API_KEY is configured."""
    api_key = get_settings().brave_search_api_key.strip()
    if not api_key:
        return []

    url = f"{BRAVE_SEARCH_URL}?{urllib.parse.urlencode({'q': query, 'count': str(limit)})}"

    def read() -> str:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read(800_000).decode("utf-8", errors="replace")

    try:
        payload = json.loads(await asyncio.to_thread(read))
    except Exception as error:
        logger.warning("web.brave_search.failed", error=str(error))
        return []

    results: list[dict[str, str]] = []
    for item in payload.get("web", {}).get("results", []):
        url_value = str(item.get("url") or "")
        if not url_value or not _is_safe_public_url(url_value):
            continue
        results.append({
            "title": _clean_text(str(item.get("title") or "Untitled")),
            "url": url_value,
            "snippet": _clean_text(str(item.get("description") or "")),
        })
        if len(results) >= limit:
            break
    return results


async def fetch_public_url(url: str, *, max_chars: int | None = None) -> dict[str, Any]:
    """Fetch and extract text from a public HTTP(S) page."""
    _ensure_web_enabled()
    settings = get_settings()
    url = url.strip()
    if not _is_safe_public_url(url):
        raise WebAccessError("Only public http(s) URLs are allowed.")

    html_text = await asyncio.to_thread(_read_url, url)
    extractor = TextExtractor()
    extractor.feed(html_text)
    text = _clean_text(" ".join(extractor.parts))
    limit = max_chars or settings.ai_office_web_fetch_max_chars
    return {
        "url": url,
        "content": text[:limit],
        "truncated": len(text) > limit,
    }


async def build_web_context(task: str, *, max_results: int = 3) -> str:
    """Return compact search context for prompts."""
    if not should_use_web_context(task):
        return ""
    results = await search_public_web(task, max_results=max_results)
    if not results:
        return (
            "Актуальный публичный web-контекст (read-only search): "
            "поиск был выполнен, но безопасные результаты не найдены. "
            "Не говори, что у тебя нет доступа к интернету; скажи, что поиск не вернул источников, "
            "и предложи уточнить запрос или проверить конкретные сайты."
        )
    lines = ["Актуальный публичный web-контекст (read-only search):"]
    for index, result in enumerate(results, start=1):
        lines.append(
            f"[{index}] {result.get('title', 'Untitled')}\n"
            f"url={result.get('url', '')}\n"
            f"snippet={result.get('snippet', '')}"
        )
    lines.append(
        "Используй этот контекст как свежие публичные сигналы. "
        "Не говори, что у тебя нет доступа к интернету, если этот блок содержит результаты. "
        "В ответе укажи источники URL из этого блока."
    )
    return "\n".join(lines)


def should_use_web_context(task: str) -> bool:
    """Heuristic for when fresh public context is likely needed."""
    text = task.lower()
    markers = (
        "актуаль",
        "сегодня",
        "сейчас",
        "новост",
        "последн",
        "latest",
        "current",
        "today",
        "news",
        "price",
        "цена",
        "курс",
        "документац",
        "docs",
        "changelog",
        "release",
        "github",
        "рынок",
        "конкурент",
        "закон",
        "налог",
    )
    return any(marker in text for marker in markers)


@tool
async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search public web pages read-only. No login, forms, purchases, or private URLs."""
    results = await search_public_web(query, max_results=max_results)
    return {"status": "ok", "query": query, "results": results}


@tool
async def fetch_web_page(url: str, max_chars: int = 6000) -> dict[str, Any]:
    """Fetch text from a public HTTP(S) page read-only. Blocks localhost/private URLs."""
    try:
        page = await fetch_public_url(url, max_chars=max_chars)
    except WebAccessError as error:
        return {"status": "blocked", "url": url, "error": str(error)}
    return {"status": "ok", **page}
