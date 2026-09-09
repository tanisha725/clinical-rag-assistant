# PROJECT_AUDIT.md

Audit date: 2026-09-09
Scope: complete read of every file in the repository (no code assumed, all verified by reading source).

---

## 1. Current project purpose

A clinical/medical Q&A assistant. The knowledge base (`docs/`) contains public-health PDFs (antibiotic safety, C. diff, TB, sickle cell disease, doxy-PEP). The intended pipeline is: user asks a health question → optionally retrieve relevant chunks from the PDFs → send question (+ context) to a local LLM via Ollama → return an answer. This is a reasonable, keepable use case for the assignment and should NOT be changed.

## 2. Current architecture

Three FastAPI services plus a leftover root-level monolith:

```
app_service   (port 8000, exposed)  -- orchestrator, calls retrieval + llm
retrieval_service (port 8000, internal) -- embeds query, searches ChromaDB
llm_service   (port 8000, internal) -- calls Ollama /api/generate
ollama        (port 11434, exposed) -- image: ollama/ollama
```

Declared in `docker-compose.yml`. There is no frontend service of any kind — no Gradio, no HTML, nothing. The only way to use the system today is `curl`/Postman against `app_service:8000/chat`.

There is also a **root-level `main.py`** that is a self-contained, single-file version of the whole pipeline (embeds queries itself, talks directly to ChromaDB and to `localhost:11434`). This looks like an early Exercise-1/2/3 prototype that predates the service split in Exercise 4, and was never deleted. It is dead code — nothing imports or runs it, and `docker-compose.yml` never builds it.

## 3. Current services

| Service | File | Responsibility today |
|---|---|---|
| app_service | `app_service/main.py` | Receives `POST /chat`, optionally calls retrieval, builds a prompt, calls llm_service, returns `{"answer": ...}` |
| retrieval_service | `retrieval_service/main.py` | `POST /retrieve`: embeds question with `all-MiniLM-L6-v2`, queries Chroma collection `clinical_docs`, returns raw chunk text list |
| llm_service | `llm_service/main.py` | `POST /generate`: forwards prompt to `http://ollama:11434/api/generate` with model `llama3.2:1b`, returns `{"answer": ...}` |
| ollama | docker image `ollama/ollama` | Runs the model server; no model is ever pulled by any script or compose step |

None of the services expose a `/health` endpoint. None validate input beyond Pydantic's basic type checking.

## 4. Current APIs

- `app_service`: `POST /chat` — body `{message: str, use_rag: bool=True}` → response `{"answer": str}`. No `sources`, no `retrieved_context`, no `similarities`, no `used_rag` echoed back, no `top_k` parameter.
- `retrieval_service`: `POST /retrieve` — body `{question: str, k: int=3}` → response `{"chunks": [str, ...]}`. Distances/similarity scores from Chroma are discarded (`results["documents"][0]` only — `results["distances"]` and `results["metadatas"]` are fetched by Chroma but never read).
- `llm_service`: `POST /generate` — body `{prompt: str}` → response `{"answer": str}`.

No OpenAPI customization, no `/health` anywhere, no root `GET /`.

## 5. Current LLM implementation

`llm_service/main.py` does a single `requests.post` to Ollama's `/api/generate` with `stream=False`, `options.num_predict=150`, no timeout, and no error handling. If Ollama is down or returns an error body, `response.json()["response"]` raises an unhandled `KeyError`/`JSONDecodeError` and the client gets a raw 500 with a stack trace.

## 6. Current Ollama implementation

Ollama runs as a plain `ollama/ollama` container in `docker-compose.yml` with a named volume `ollama_data` for model storage. **No step anywhere pulls a model** — not in the Dockerfile, not in compose, not in any script. On a clean `docker compose up`, the first `/generate` call will fail because the model doesn't exist in the container yet. A human has to manually `docker exec` in and run `ollama pull llama3.2:1b`.

## 7. Current model

**`llama3.2:1b`** — used in three separate places, hardcoded as a literal string:
- `llm_service/main.py` line 13
- root `main.py` line 61
- `llm_service/tempCodeRunnerFile.py` (a stray VS Code "Code Runner" artifact file containing only the text `llama3.2:1b` — not executable code, just leftover clutter)

**This does not satisfy the assignment requirement.** The assignment explicitly requires Ollama + **Code Llama**, and explicitly warns that `llama3.2:1b` does not count. This is the single most important correctness gap in the project.

## 8. Current knowledge base

`docs/` (root) and `retrieval_service/docs/` both exist and are near-duplicates:
- `retrieval_service/docs/` has 4 PDFs.
- root `docs/` has those same 4 PDFs **plus 2 more** (`AntibioticSafety-Patients-P.pdf` and `what-you-should-know-about-scd.pdf`) that are missing from `retrieval_service/docs/`.

Since the Dockerfile runs `python build_kb.py` at **image build time** inside `retrieval_service/`, only the 4 PDFs in `retrieval_service/docs/` actually get ingested — the other 2 documents at the root are silently never indexed. Both `docs/` folders also contain a stray `.DS_Store` (macOS clutter, not filtered — though the loader does skip dotfiles by name check, so it's harmless but should be removed/gitignored).

## 9. Current chunking

`build_kb.py` (present in three copies — see §16) does simple whitespace-word chunking:
```python
def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    ...
```
Chunk size (500 words) and overlap (50 words) are hardcoded function-default arguments, not configurable via env var or CLI flag, and duplicated across 3 identical files. No sentence/paragraph awareness, no minimum-chunk filtering (an empty/near-empty final chunk is possible), no per-chunk ID scheme beyond a global incrementing counter.

## 10. Current embeddings

Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim), loaded identically in `build_kb.py` and `retrieval_service/main.py`. This is a reasonable, lightweight, CPU-friendly choice — appropriate to keep. It is NOT documented anywhere (no mention of dimension, resource needs, or rationale).

## 11. Current vector database

ChromaDB, `PersistentClient(path="./chroma_db")`, collection name `clinical_docs`. Reasonable choice, worth keeping. Problems:
- The persistent path is relative (`./chroma_db`), resolved inside the container's working directory — no Docker volume is mounted for it in `docker-compose.yml`, so the ingested index only survives because it was baked into the image at `docker build` time (via `RUN python build_kb.py`). Removing/rebuilding the image without cache wipes and re-ingests it every time (slow, and couples KB content to image builds rather than a runtime/volume step).
- No metadata beyond `{"source": filename}` — no `chunk_id`, no `doc_id`, no page number.

## 12. Current retrieval

`retrieval_service/main.py`: embeds the question, calls `collection.query(..., n_results=k)`, returns only `results["documents"][0]`. Similarity/distance scores and metadata (source filenames) are computed by Chroma but discarded before the response is built. `k` is a request field but nothing upstream (app_service) ever sets it — it silently defaults to 3 always.

## 13. Current RAG implementation

In `app_service/main.py`: if `use_rag`, call retrieval, join chunks with `\n\n`, wrap in a prompt (`"Answer using only this context:\n{context}\n\nQuestion: {q}\nAnswer:"`), send to llm_service. This is a real (not faked) RAG loop — retrieval genuinely happens and genuinely changes the prompt. However:
- **Critical bug**: both the retrieval call and the generate call are sent to `http://localhost:8000/...` (`app_service/main.py` lines 15 and 20). Inside a Docker container, `localhost` refers to the `app_service` container itself, not `retrieval_service` or `llm_service`. Since neither of those routes exists inside `app_service`, **every `/chat` call will fail in the current `docker-compose` setup** — this is the most severe functional bug in the codebase, not a hypothetical.
- The prompt has no system instructions, no "say so if the answer isn't in context" instruction, no guardrail against fabrication.
- No sources, retrieved chunks, or similarity scores are returned to the caller, so there is no way to *prove* to a viewer that retrieval actually happened — this fails the assignment's explicit RAG-vs-non-RAG demonstrability requirement.
- No top_k control is exposed end-to-end.

## 14. Current Docker implementation

Three near-identical Dockerfiles (`python:3.11-slim`, copy requirements, pip install, copy code, uvicorn on port 8000). Issues:
- `retrieval_service/Dockerfile` runs `RUN python build_kb.py` during image build — this means the container image itself contains a full copy of `sentence-transformers` model weights plus the resulting Chroma index baked in as image layers. Rebuilding requires network access to download the embedding model at build time and makes the image large.
- No `.dockerignore` anywhere, so `__pycache__`, `.DS_Store`, and (for retrieval_service) large PDFs all get shipped into build context/image without filtering.
- No `HEALTHCHECK` directives in any Dockerfile.
- `docker-compose.yml` has no explicit `networks:` block (fine — compose's default network still allows name-based DNS) but has no healthchecks and `depends_on` is the bare form (only waits for container start, not readiness) — `app_service` can start before `llm_service`/`retrieval_service`/`ollama` are actually able to serve requests.
- No volume is mounted for `retrieval_service`'s `chroma_db`, and none for re-running ingestion without a full image rebuild.
- No image is ever pushed anywhere (no ECR references) — there is currently no cloud deployment path at all, despite the assignment requiring one.

## 15. Current frontend

**None exists.** There is no `frontend/` directory, no Gradio code, no HTML, no CLI chat script — nothing. The only current way to interact with the system is a raw HTTP client hitting `app_service`'s `/chat` endpoint. This is a complete gap against the assignment's explicit frontend requirement.

## 16. Existing bugs (functional, not stylistic)

1. **Service-to-service URLs use `localhost` instead of Docker service names** (`app_service/main.py:15,20`) — breaks all `/chat` calls under `docker-compose`. This is the most severe bug in the repo.
2. **Wrong model** — `llama3.2:1b` used everywhere instead of the required Code Llama.
3. **No model pull step** — Ollama container starts with zero models; first real request fails until someone manually pulls a model.
4. Root `docs/` has 6 PDFs, `retrieval_service/docs/` (the one actually ingested) has only 4 — two documents are silently never indexed.
5. `response.json()["response"]` in both `llm_service/main.py` and the dead root `main.py` will raise unhandled exceptions if Ollama returns an error payload (e.g., model not found) — surfaces as an opaque 500.
6. No timeouts on any `requests.post` call — a hung Ollama or retrieval call blocks the request indefinitely.
7. `retrieval_service`'s `k` parameter is never actually driven by the caller (app_service never passes it), so "configurable top-k" doesn't work end-to-end even though the field exists.
8. Chroma's returned distances/metadatas are computed but discarded, so no similarity scores or source attribution ever reach the end user.

## 17. Missing requirements (per assignment)

- No frontend (Gradio or otherwise).
- No Code Llama usage (Exercise 1's core requirement).
- No `/health` endpoints on any service.
- No `.env` / `.env.example`, no environment-variable-driven configuration anywhere — all URLs and the model name are hardcoded string literals duplicated across files.
- No tests directory / test suite.
- No README, ARCHITECTURE.md, API.md, EXERCISES.md, or VIVA_GUIDE.md.
- No AWS/cloud deployment story of any kind.
- No logging (no `logging` module usage anywhere; the only observability is FastAPI/uvicorn's default access log).
- No CORS configuration.
- No `.gitignore` (and the folder isn't even a git repo yet — `git` was not initialized).
- No source/similarity/context data surfaced in any API response — fails the "prove RAG happened" demonstration requirement.

## 18. Incorrect implementation (design-level, not just missing)

- Chunking, embedding-model loading, and Chroma connection logic are copy-pasted verbatim across `build_kb.py` (root), `build_kb 2.py` (root), and `retrieval_service/build_kb.py` — three copies of the same ~40 lines, one of which (`build_kb 2.py`) is a pure accidental duplicate (likely from a macOS "Save As" or file-manager copy).
- Ingestion is coupled to Docker image build (`RUN python build_kb.py` inside the Dockerfile) rather than being a runtime/one-off script — this is workable for a demo but is not how the assignment's "ingestion pipeline" is meant to be demonstrated (re-running ingestion requires a full image rebuild).
- The dead root-level `main.py` duplicates the entire pipeline logic a third time (a third copy of the RAG prompt, a third hardcoded model name, a third embedding load) and risks confusing anyone reading the repo about which code path is "real."

## 19. Technical risks

- **Cost/compute**: Code Llama (7B) via Ollama needs realistic CPU inference resources (~8GB+ RAM minimum for a quantized 7B model) — cannot run on typical free-tier or micro AWS instances; must be sized deliberately (see recommended architecture) and stopped when not in use.
- **Model pull time**: pulling a 7B model on first boot takes several minutes and several GB of network/disk — needs to happen once, persisted to a volume, not on every container restart.
- **Build-time ingestion coupling**: baking the vector DB into the Docker image means every doc change requires a full rebuild; acceptable for a student demo but should be called out as a simplification, not hidden.
- **No git repository yet**: nothing here is version-controlled; a `.gitignore` must be created *before* the first commit so `chroma_db/`, `__pycache__/`, `.DS_Store`, and `.env` never get committed.

## 20. Recommended final architecture

Keep the existing 3-service split (it already matches the assignment's suggested Exercise 4 architecture) and add a frontend service:

```
Gradio Frontend (frontend/, local or containerized)
        │  HTTP
        ▼
Application/Orchestration Service (app_service) — FastAPI, /chat, /health
        │                              │
        ▼                              ▼
Retrieval Service (retrieval_service)   LLM Service (llm_service)
  /retrieve, /health                      /generate, /health
        │                                     │
        ▼                                     ▼
   ChromaDB (persistent volume)          Ollama (cloud, e.g. AWS EC2)
                                               │
                                               ▼
                                          Code Llama (codellama:7b-instruct, or
                                          codellama:7b-instruct-q4_0 for lighter RAM)
```

Concrete fixes to implement next (not done yet — this document is the audit only):
1. Fix `app_service` to call `http://retrieval_service:8000/retrieve` and `http://llm_service:8000/generate` using env vars, not hardcoded `localhost`.
2. Switch the model everywhere to a real Code Llama tag (e.g. `codellama:7b-instruct-q4_K_M`), driven by a single `OLLAMA_MODEL` env var, documented with resource requirements.
3. Add a model-pull step (compose `entrypoint`/init container or a documented one-time `ollama pull` command) so Ollama isn't silently empty on first boot.
4. Consolidate the three duplicate `build_kb.py` copies into one, in `retrieval_service/`, parameterized by `CHUNK_SIZE`/`CHUNK_OVERLAP` env vars; delete the root-level duplicates and dead `main.py`.
5. Return sources + similarity scores + retrieved chunks from `/retrieve` and surface them through `/chat`, so RAG-on vs RAG-off is provably different in the UI.
6. Build a Gradio frontend with a RAG on/off toggle, top-k slider, and a context/sources panel.
7. Add `/health` to all three services, add timeouts + try/except error handling around every outbound HTTP call, add basic logging.
8. Add `.env.example`, wire every URL/model/chunk-size value through environment variables.
9. Move Ollama + Code Llama to an AWS EC2 instance sized for 7B CPU inference (documented shutdown procedure to avoid idle billing); keep the frontend/app/retrieval services light enough to run locally in Docker or on a small instance.
10. Add `.gitignore`, `tests/`, `README.md`, `ARCHITECTURE.md`, `API.md`, `EXERCISES.md`, `VIVA_GUIDE.md`.
11. Clean up: delete `build_kb 2.py`, root `main.py`, `retrieval_service/docs/` (keep root `docs/` as the single source of truth, since it's the complete set of 6), `llm_service/tempCodeRunnerFile.py`, all `__pycache__/` and `.DS_Store` files.

---

**This document reflects the repository as it exists today. No code has been changed yet.**
