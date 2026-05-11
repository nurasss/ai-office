# AI Office coding standards

> Parsed source metadata
>
> - Owner: `developer`
> - Source id: `code_style_guides`
> - Source file: `data/raw_knowledge/developer/style_guides/local__python_project_style.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# AI Office coding standards

## Python

- Use type hints for public functions and non-trivial internal helpers.
- Keep async boundaries explicit; do not block inside async request handlers.
- Prefer small functions with clear responsibilities.
- Log with the project logger from `core.logger`.
- Raise explicit errors for unsupported agent ids, backends or missing sources.
- Keep comments focused on why a block exists.

## RAG and knowledge code

- Use `rag.namespaces.get_agent_profile` for namespace decisions.
- Do not hard-code allowed namespaces in agent logic.
- Preserve metadata fields when indexing documents.
- Keep `common_corporate` separate from agent namespaces.
- Treat `data/` as runtime storage, not source knowledge.

## API

- Use Pydantic request and response models for stable API contracts.
- Return route-only results without calling an LLM.
- Keep user-facing errors concise and avoid leaking secrets.
- Keep Telegram notifications optional.

## Tests

When changing RAG behavior, cover:

- namespace filter construction;
- foreign namespace blocking;
- local vector store filtering;
- source catalog loading;
- route-only behavior when relevant.
