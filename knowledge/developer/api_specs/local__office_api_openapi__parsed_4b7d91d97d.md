# local__office_api_openapi

> Parsed source metadata
>
> - Owner: `developer`
> - Source id: `api_specs`
> - Source file: `data/raw_knowledge/developer/api_specs/local__office_api_openapi.yaml`
> - Source format: `yaml`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# local__office_api_openapi

```yaml
openapi: 3.0.3
info:
  title: AI Office Product API
  version: "1.0.0"
paths:
  /api/office/routes:
    post:
      summary: Route a task through PMO without invoking the destination agent
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - task
              properties:
                task:
                  type: string
                  minLength: 1
      responses:
        "200":
          description: Route result
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  task:
                    type: string
                  handled_by:
                    type: string
                  handled_by_name:
                    type: string
                  subtasks:
                    type: array
                    items:
                      type: object
  /api/office/tasks:
    post:
      summary: Submit a task to AI Office
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/OfficeTaskRequest"
      responses:
        "200":
          description: Task result or route-only response
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OfficeTaskResponse"
        "400":
          description: Missing LLM credentials or invalid execution state
        "404":
          description: Unknown agent
components:
  schemas:
    OfficeTaskRequest:
      type: object
      required:
        - task
      properties:
        task:
          type: string
          minLength: 1
        agent_id:
          type: string
          default: pmo
        route_only:
          type: boolean
          default: false
        notify_telegram:
          type: boolean
          default: false
    RagHit:
      type: object
      properties:
        namespace:
          type: string
        source:
          type: string
        score:
          type: number
    OfficeTaskResponse:
      type: object
      properties:
        status:
          type: string
        task_id:
          type: string
        requested_agent:
          type: string
        handled_by:
          type: string
        handled_by_name:
          type: string
        result:
          type: string
        route:
          type: object
        rag_hits:
          type: array
          items:
            $ref: "#/components/schemas/RagHit"
        telegram_notified:
          type: boolean
```
