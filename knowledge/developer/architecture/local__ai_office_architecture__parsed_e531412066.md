# AI Office architecture

> Parsed source metadata
>
> - Owner: `developer`
> - Source id: `architecture_schemes`
> - Source file: `data/raw_knowledge/developer/architecture/local__ai_office_architecture.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# AI Office architecture

## Runtime

AI Office is a FastAPI application with seven Python agent classes and a PMO
orchestration flow. The app exposes web routes and product API routes.

## Main modules

| Path | Responsibility |
|---|---|
| `agents/` | Agent implementations |
| `prompts/` | System prompts per agent |
| `api/office.py` | Product API for tasks and routing |
| `web/app.py` | Web interface and chat API |
| `rag/` | Retriever, namespace policy and vector store backends |
| `knowledge/` | Source Markdown/TXT/PDF documents for RAG |
| `scripts/ingest_knowledge.py` | Ingest source files into vector store |
| `memory/` | Long-term JSONL memory |
| `tools/external/` | Slack, Jira, GitHub, DB, ERP and Telegram tool wrappers |
| `config/settings.yaml` | Agent and RAG configuration |
| `config/knowledge_sources.yaml` | Source catalog and namespace mapping |

## RAG flow

1. Source files live in `knowledge/<agent>/<source>/`.
2. `scripts/ingest_knowledge.py` reads the source catalog.
3. Files are chunked according to `rag.chunk_size` and `rag.chunk_overlap`.
4. Chunks are stored with metadata: `agent_id`, `namespace`, `source_id`,
   `source`, `chunk_index`.
5. `Retriever` adds namespace filters at query time so every agent reads only
   common plus its own namespace.

## Local vector store

For development the project uses `local_json`, stored at:

```text
data/vector_store/documents.jsonl
```

This store uses token overlap search. It is suitable for smoke tests, not for
production semantic search.

## Production vector store

The repository contains stubs for `pgvector` and `pinecone`. Production work
must implement embeddings, upsert and similarity search before relying on those
backends.
