"""Load agent-specific knowledge files into the configured vector store.

Examples:
    python3 scripts/ingest_knowledge.py --agent copywriter
    python3 scripts/ingest_knowledge.py --agent all --include-common
    python3 scripts/ingest_knowledge.py --agent pmo --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_agent_config
from rag.namespaces import COMMON_NAMESPACE, all_agent_namespaces, get_agent_profile
from rag.retriever import Retriever

SUPPORTED_TEXT_FORMATS = {".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".sql"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index isolated agent RAG sources.")
    parser.add_argument(
        "--agent",
        default="all",
        help="Agent id to index: pmo, copywriter, developer, support, data_analyst, accountant, strategist, or all.",
    )
    parser.add_argument(
        "--include-common",
        action="store_true",
        help="Also index common corporate sources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be indexed without writing to the vector store.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    agent_namespaces = all_agent_namespaces()
    agent_ids = list(agent_namespaces) if args.agent == "all" else [args.agent]

    unknown_agents = [agent_id for agent_id in agent_ids if agent_id not in agent_namespaces]
    if unknown_agents:
        raise SystemExit(f"Unknown agent id(s): {', '.join(unknown_agents)}")

    retriever = Retriever()

    if args.include_common:
        common_documents = collect_common_documents()
        await index_or_print(
            retriever=retriever,
            documents=common_documents,
            agent_id="common",
            namespace=COMMON_NAMESPACE,
            dry_run=args.dry_run,
        )

    for agent_id in agent_ids:
        profile = get_agent_profile(agent_id)
        documents = collect_agent_documents(agent_id)
        await index_or_print(
            retriever=retriever,
            documents=documents,
            agent_id=agent_id,
            namespace=profile["namespace"],
            dry_run=args.dry_run,
        )


def collect_common_documents() -> list[dict[str, Any]]:
    catalog_path = PROJECT_ROOT / "config" / "knowledge_sources.yaml"
    with open(catalog_path, "r", encoding="utf-8") as file:
        catalog = yaml.safe_load(file) or {}

    sources = catalog.get("common", {}).get("sources", [])
    return collect_documents_from_sources(
        owner="common",
        namespace=COMMON_NAMESPACE,
        sources=sources,
    )


def collect_agent_documents(agent_id: str) -> list[dict[str, Any]]:
    profile = get_agent_profile(agent_id)
    return collect_documents_from_sources(
        owner=agent_id,
        namespace=profile["namespace"],
        sources=profile["sources"],
    )


def collect_documents_from_sources(
    *,
    owner: str,
    namespace: str,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rag_config = load_agent_config().get("rag", {})
    chunk_size = rag_config.get("chunk_size", 1024)
    chunk_overlap = rag_config.get("chunk_overlap", 128)

    documents: list[dict[str, Any]] = []
    for source in sources:
        source_path = PROJECT_ROOT / source["path"]
        if not source_path.exists():
            print(f"[skip] missing source path: {source_path}")
            continue

        allowed_suffixes = {f".{fmt.lower()}" for fmt in source.get("formats", [])}
        for path in iter_files(source_path, allowed_suffixes):
            text = read_file(path)
            if not text.strip():
                continue

            for index, chunk in enumerate(chunk_text(text, chunk_size, chunk_overlap)):
                documents.append(
                    {
                        "id": stable_id(owner, source["id"], path, index),
                        "content": chunk,
                        "metadata": {
                            "agent_id": owner,
                            "namespace": namespace,
                            "source_id": source["id"],
                            "source_title": source.get("title", source["id"]),
                            "source": str(path.relative_to(PROJECT_ROOT)),
                            "chunk_index": index,
                        },
                    }
                )

    return documents


async def index_or_print(
    *,
    retriever: Retriever,
    documents: list[dict[str, Any]],
    agent_id: str,
    namespace: str,
    dry_run: bool,
) -> None:
    print(f"{agent_id}: {len(documents)} chunks -> {namespace}")
    if not documents or dry_run:
        for document in documents[:20]:
            print(
                "  - "
                f"{document['metadata']['source']} "
                f"#{document['metadata']['chunk_index']}"
            )
        return

    await retriever.index_documents(
        documents,
        agent_id=agent_id,
        namespace=namespace,
    )


def iter_files(source_path: Path, allowed_suffixes: set[str]) -> Iterable[Path]:
    for path in sorted(source_path.rglob("*")):
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            yield path


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_FORMATS:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return read_pdf(path)
    return ""


def read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        print(f"[skip] pypdf is not installed, cannot read {path}")
        return ""

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> Iterable[str]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized:
        return

    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        yield normalized[start:end]
        if end >= len(normalized):
            break
        start = max(end - chunk_overlap, start + 1)


def stable_id(owner: str, source_id: str, path: Path, chunk_index: int) -> str:
    payload = json.dumps(
        {
            "owner": owner,
            "source_id": source_id,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "chunk_index": chunk_index,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{owner}_{source_id}_{digest}"


if __name__ == "__main__":
    asyncio.run(main())
