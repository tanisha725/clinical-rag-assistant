# API.md

Every service is a FastAPI app and serves interactive Swagger UI at `/docs` and the raw
OpenAPI schema at `/openapi.json` (e.g. `http://localhost:8000/docs` for `app_service`
when running via Docker Compose).

## app_service (Application / Orchestration Service) — port 8000, publicly reachable

### `GET /health`
Reports its own status plus a live check of both downstream services.

Response:
```json
{
  "status": "ok",
  "downstream": {
    "retrieval_service": {"status": "ok", "knowledge_base_size": 187},
    "llm_service": {"status": "ok", "ollama_reachable": true, "model": "codellama:7b-instruct-q4_K_M", "model_pulled": true}
  }
}
```

### `POST /chat`
The single orchestration entry point used by the frontend.

Request:
```json
{
  "message": "What should I know before taking antibiotics?",
  "use_rag": true,
  "top_k": 3
}
```
- `message` (string, required, min length 1)
- `use_rag` (bool, default `true`)
- `top_k` (int, 1-20, default `3`) — only used when `use_rag` is true

Response (RAG on):
```json
{
  "answer": "Take the full course exactly as prescribed...",
  "used_rag": true,
  "top_k": 3,
  "sources": ["Do-I-Need-antibiotics-Infographic-85by55-508.pdf"],
  "retrieved_context": [
    {
      "text": "Finish your antibiotics course even if you feel better...",
      "source": "Do-I-Need-antibiotics-Infographic-85by55-508.pdf",
      "chunk_id": 2,
      "similarity": 0.83
    }
  ],
  "model": null
}
```

Response (RAG off):
```json
{
  "answer": "Antibiotics are medicines used to treat bacterial infections...",
  "used_rag": false,
  "top_k": 3,
  "sources": [],
  "retrieved_context": [],
  "model": null
}
```

Errors:
- `422` — empty message, or `top_k` outside 1-20 (Pydantic validation)
- `502` — a downstream service (retrieval_service or llm_service) is unreachable or
  errored; `detail` names which one, e.g. `"llm_service is unavailable: ..."`

---

## retrieval_service — port 8000, internal only

### `GET /health`
```json
{"status": "ok", "knowledge_base_size": 187}
```

### `POST /retrieve`
Request:
```json
{"question": "What should I know before taking antibiotics?", "top_k": 3}
```
- `question` (string, required, min length 1)
- `top_k` (int, 1-20, default 3)

Response:
```json
{
  "chunks": [
    {"text": "...", "source": "abx.pdf", "chunk_id": 2, "similarity": 0.83}
  ],
  "knowledge_base_size": 187
}
```
If the knowledge base is empty, `chunks` is `[]` and `knowledge_base_size` is `0` (no
error — an empty KB is a valid, demonstrable state, not a failure).

Errors: `422` on invalid input.

---

## llm_service — port 8000, internal only

### `GET /health`
Checks Ollama's `/api/tags` to confirm both that Ollama is reachable and that the
configured model has actually been pulled:
```json
{
  "status": "ok",
  "ollama_reachable": true,
  "model": "codellama:7b-instruct-q4_K_M",
  "model_pulled": true,
  "available_models": ["codellama:7b-instruct-q4_K_M"]
}
```
`status` is `"degraded"` if Ollama is unreachable or the model hasn't been pulled yet.

### `POST /generate`
Request:
```json
{"prompt": "Answer using ONLY this context:\n...\n\nQuestion: ...\nAnswer:"}
```
Response:
```json
{"answer": "...", "model": "codellama:7b-instruct-q4_K_M"}
```
Errors:
- `422` — empty prompt
- `502` — Ollama unreachable, timed out, or the model isn't pulled; `detail` explains why

---

## Ingestion (not an HTTP API — a one-off script)

`retrieval_service/ingest.py`, run via `docker compose up kb_ingest` (or `python
ingest.py` directly). Reads every `.pdf`/`.txt` in `DOCS_DIR`, extracts + cleans text,
chunks it (`CHUNK_SIZE`/`CHUNK_OVERLAP`), embeds each chunk, and upserts into the
`clinical_docs` ChromaDB collection with `source`/`doc_id`/`chunk_id` metadata. Safe to
re-run — upserts, not appends, so re-running on unchanged files does not create
duplicate vectors.
