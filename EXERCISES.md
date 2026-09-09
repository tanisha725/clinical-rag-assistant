# EXERCISES.md

This is **one application** (the Clinical RAG Assistant) developed progressively across
five exercises. Each section below explains what that exercise added, exactly which files
implement it today, and how to demonstrate/test it.

---

# Exercise 1 — Basic LLM Application

**Objective:** show an application talking to Code Llama through Ollama's API, with no
retrieval involved yet.

**Architecture:** `User → Frontend → app_service /chat → llm_service /generate → Ollama → Code Llama`

**Files:** `llm_service/main.py`, `llm_service/ollama_client.py`, `llm_service/config.py`

**Implementation:** `llm_service` wraps a single call to Ollama's `POST /api/generate`
with `model=codellama:7b-instruct-q4_K_M`, `stream=false`. Timeouts and connection errors
are caught and surfaced as HTTP 502s instead of crashing.

**API:** `POST /generate {"prompt": "..."}` → `{"answer": "...", "model": "..."}` (see
[API.md](API.md)).

**Request flow:** frontend or any HTTP client → `app_service /chat` with `use_rag:false`
→ `llm_service /generate` → Ollama → Code Llama → answer flows straight back, unmodified.

**Testing:** `tests/test_llm_service.py` mocks `requests.post` to Ollama and asserts:
success path returns the model's answer; connection errors and timeouts both return 502;
an empty prompt is rejected with 422; `/health` correctly reports whether the model has
actually been pulled.

**Expected result:** asking a question with RAG off returns a plausible but *unverified*
answer generated purely from the model's training data — it may be right, incomplete, or
occasionally wrong, and there is no way to check its source.

**Viva explanation:** "This is the simplest possible LLM integration — my app sends a
prompt string to Ollama's REST API, Ollama runs it through Code Llama, and returns
generated text. No context, no memory, no retrieval — just next-token prediction over the
raw prompt."

---

# Exercise 2 — Knowledge Base

**Objective:** build a real ingestion pipeline that turns the PDF documents in `./docs`
into a searchable vector index, ready for Exercise 3 to query.

**Documents:** 6 CDC/public-health PDFs in `./docs` — antibiotic safety (2 documents), C. diff, TB, doxy-PEP, sickle cell disease.

**Text processing:** `retrieval_service/ingest.py::extract_text` uses `pypdf` to pull raw
text per page; `clean_text` collapses repeated whitespace/blank lines left over from PDF
extraction artifacts.

**Chunking:** `retrieval_service/chunking.py::chunk_text` — word-count based sliding
window.
- `CHUNK_SIZE=500` words: large enough to keep a full clinical instruction/paragraph
  together (most source PDFs are short handouts, not dense papers), small enough to stay
  well inside the LLM's context window even with several chunks retrieved at once.
- `CHUNK_OVERLAP=50` words (10%): prevents a sentence that straddles a chunk boundary
  from losing its meaning on either side of the cut.
- Both values are environment-configurable (`.env` → `CHUNK_SIZE`, `CHUNK_OVERLAP`), not
  hardcoded, so they can be tuned without touching code.

**Embeddings:** `retrieval_service/embeddings.py` loads
`sentence-transformers/all-MiniLM-L6-v2` once (cached) and encodes each chunk into a
384-dimension vector. Chosen because it's small (~90MB), fast enough for CPU-only
inference, and standard for short-document semantic search.

**Vector representation / KB construction:** `retrieval_service/vector_store.py` upserts
each chunk into a ChromaDB collection (`clinical_docs`) as
`{id, embedding, document_text, metadata: {source, doc_id, chunk_id}}`. Upsert (not add)
makes re-ingestion idempotent.

**Testing:** `tests/test_chunking.py` checks chunk counts, overlap correctness, and edge
cases (empty text, text shorter than one chunk, zero overlap).

**Expected result:** running `docker compose up kb_ingest` prints `Indexed N chunks from 5
documents` and leaves a populated ChromaDB collection ready for querying.

**Viva explanation:** "Before any question is asked, I turn my documents into vectors
offline: extract text, clean it, split it into overlapping ~500-word chunks so nothing
gets cut off mid-sentence, embed each chunk into a 384-dimension vector with a
sentence-transformer, and store it in ChromaDB alongside metadata about which document and
chunk it came from."

---

# Exercise 3 — Retrieval + RAG

**Query embedding:** `retrieval_service/main.py::retrieve` embeds the incoming question
with the same `all-MiniLM-L6-v2` model used at ingestion time — queries and documents must
share an embedding space to be comparable.

**Vector similarity:** ChromaDB's `collection.query(...)` performs a nearest-neighbor
search over L2 distance; `retrieval_service` converts distance to a bounded
`similarity = 1 / (1 + distance)` score for the frontend.

**Top-k:** `top_k` is a request field (`RetrieveRequest.top_k`, 1-20, default 3),
threaded all the way from the Gradio slider → `app_service /chat` → `retrieval_service
/retrieve` — genuinely configurable end to end (this was previously broken/dead in the
original code; see PROJECT_AUDIT.md §16 item 7).

**Retrieval:** returns each chunk's text, source filename, chunk id, and similarity score
— not just bare text — so the frontend can prove where an answer came from.

**Context construction:** `app_service/services/orchestrator.py::handle_chat` joins
retrieved chunks (prefixed with `[source filename]`) into one context block.

**RAG prompt:** (`orchestrator.RAG_SYSTEM_PROMPT`) explicitly instructs the model to
answer *only* from the given context, never fabricate facts or sources, and to respond
with an exact "not found in the available knowledge base" sentence when the context is
insufficient — this is what makes the RAG-off vs RAG-on comparison meaningful rather than
cosmetic.

**RAG vs Non-RAG:** the same `/chat` endpoint takes a `use_rag` boolean:
- `use_rag=false` → question sent to `llm_service` verbatim, `sources`/`retrieved_context`
  come back empty, frontend shows a "RAG OFF" banner.
- `use_rag=true` → full retrieve → context → grounded-prompt → generate pipeline runs,
  and the frontend shows a "RAG ON" banner plus every retrieved chunk (source, chunk id,
  similarity) and the deduplicated source list.

**Testing:** `tests/test_retrieval_service.py` covers similarity ordering, empty-KB
behavior, and input validation. `tests/test_app_service.py` covers both RAG paths, the
"no chunks matched" case, and 502 propagation when either downstream service fails.

**Expected result:** the same question asked twice — once with RAG off, once with RAG on
— visibly differs: the RAG-on answer only uses facts traceable to a listed source PDF, and
explicitly says "not found" for anything outside `./docs`, while RAG-off answers from the
model's general training.

**Viva explanation:** "I embed the user's question with the same model I used at
ingestion, search ChromaDB for the top-k nearest chunks by vector similarity, and build a
prompt that hands the model only that context — with an explicit instruction not to
invent anything beyond it. Toggling RAG off skips all of that and sends the raw question
straight to the model, so the two behave visibly differently on the same input."

---

# Exercise 4 — APIs, Services and Orchestration

**Service architecture:**
- **Frontend Service** (`frontend/`) — Gradio UI, calls `app_service` only.
- **Application/Orchestration Service** (`app_service/`) — validates requests, decides
  RAG vs non-RAG, calls the other two services, builds the RAG prompt, returns a
  structured response.
- **Retrieval Service** (`retrieval_service/`) — query embedding, vector search, top-k,
  similarity, metadata/source info; also owns the ingestion pipeline.
- **LLM Service** (`llm_service/`) — the only service that talks to Ollama.
- **Knowledge Base / data layer** — `./docs` (source PDFs) + a ChromaDB volume (vector
  storage), owned by `retrieval_service`.

**Responsibilities are enforced by ownership, not convention** — e.g. only
`llm_service` imports `requests` to call Ollama; `app_service` never talks to Ollama
directly, and never touches ChromaDB directly.

**API communication:** all inter-service calls are plain HTTP + JSON via FastAPI/Pydantic
models, addressed by **Docker Compose service name** (`http://retrieval_service:8000`,
`http://llm_service:8000`) — never `localhost`, which was the critical bug in the
pre-refactor version (PROJECT_AUDIT.md §13/§16 item 1).

**Orchestration / request lifecycle:** see ARCHITECTURE.md's sequence diagrams. In short,
`app_service` is the only service the frontend talks to; it fans out to retrieval and LLM
services and merges their results into one response.

**Error handling:** every outbound `requests` call in every service has an explicit
timeout and try/except; failures surface as typed errors
(`UpstreamServiceError`/`OllamaError`) that map to HTTP 502 with a message naming which
downstream service failed, instead of an opaque 500 stack trace.

**Testing:** each service's test file mocks its outbound HTTP calls (`requests.post`)
rather than requiring the other services or Ollama to actually be running — see
`tests/conftest.py` for how each service's modules are imported in isolation.

**Viva explanation:** "I split what used to be a monolith into four independently
deployable services, each with one job, talking over HTTP the same way they would over
the network in production. `app_service` is the orchestrator — it never knows *how*
retrieval or generation happen, only that it can POST to `/retrieve` and `/generate` and
get JSON back. That's what makes it possible to scale, replace, or redeploy any one piece
(e.g. swap ChromaDB for another vector DB, or Ollama for a different LLM host) without
touching the others."

---

# Exercise 5 — Docker

**Docker architecture:** five containers — `frontend`, `app_service`, `retrieval_service`,
`llm_service`, `ollama` — plus two one-off jobs (`ollama_pull`, `kb_ingest`) that prepare
state before the long-running services start. See ARCHITECTURE.md's Docker diagram.

**Dockerfiles:** each service has its own minimal `python:3.11-slim`-based Dockerfile
(`COPY requirements.txt` → `pip install` → `COPY . .` → `CMD uvicorn ...`), each with a
`HEALTHCHECK` hitting its own `/health` endpoint, and a `.dockerignore` excluding
`__pycache__`, `.DS_Store`, and (for retrieval_service) the runtime `chroma_db/` directory.

**Containers / networking:** `docker-compose.yml` defines one implicit default network;
every service resolves every other by its Compose service name (enforced project-wide —
see Exercise 4). `retrieval_service` mounts `./docs` read-only and a named volume
`chroma_data` for the persistent vector index; `ollama` mounts a named volume
`ollama_data` so a pulled model survives container restarts.

**Environment variables:** every URL, model name, timeout, chunk size, and top-k default
comes from `.env` (see `.env.example`) via each service's `config.py` — nothing is
hardcoded, and the same image can point at a different Ollama host (e.g. local Docker vs.
an AWS EC2 instance) purely by changing `OLLAMA_URL`.

**Docker Compose:** `ollama_pull` and `kb_ingest` are one-off jobs gated with
`depends_on: condition: service_completed_successfully`, so `llm_service` never starts
before the model exists and `retrieval_service` never starts before the KB is built.

**Cloud deployment:** the exact same `docker-compose.yml` runs unmodified on a single AWS
EC2 instance (see README.md §15 and ARCHITECTURE.md's AWS diagram) — no code changes
between "local Mac demo" and "cloud demo," only which `.env` values point where.

**Testing:** `docker compose config` validates the compose file; `docker compose up
--build` end-to-end is the integration test (not part of the automated `pytest` suite,
which deliberately avoids requiring Docker/Ollama — see PROJECT_AUDIT.md's testing
guidance and README.md §19).

**Viva explanation:** "Every piece of the pipeline is a container. Two jobs run once and
exit — pulling the model and building the vector index — everything else runs
continuously. Because every URL is an environment variable and every container is
addressed by name, the identical compose file that runs on my Mac for development also
runs unmodified on a single AWS EC2 instance for the real demo — only the `.env` values
change, never the code."
