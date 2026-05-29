# Successful ticket example: route-only check

> Parsed source metadata
>
> - Owner: `support`
> - Source id: `successful_tickets`
> - Source file: `data/raw_knowledge/support/successful_tickets/local__route_only_ticket_example.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Successful ticket example: route-only check

## User question

How can I check which agent will handle my task without spending model tokens?

## Support answer

Use route-only mode. It returns the selected agent, route metadata and RAG hits,
but does not invoke the final LLM call.

For the product API, send:

```bash
curl -X POST http://localhost:8000/api/office/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Напиши пост о запуске AI Office","agent_id":"pmo","route_only":true}'
```

## Resolution

The user can verify PMO routing and source matching before running a paid model
call.

## Confidence

High for local prototype behavior.
