# Clinical RAG Assistant

A retrieval-augmented generation (RAG) application that answers public-health / clinical
questions (antibiotics, C. diff, TB, sickle cell disease, doxy-PEP) using **Ollama + Code
Llama**, grounded in a small knowledge base of CDC/public-health PDFs.

This single application was built incrementally across five exercises (see
[EXERCISES.md](EXERCISES.md)): a bare LLM call → a knowledge base → retrieval + RAG →
a multi-service architecture → containerization.

## 1. Problem statement

Large language models answer confidently even when they don't actually know something —
this is especially risky for medical/health questions. This project demonstrates how
**retrieval-augmented generation** grounds an LLM's answers in a fixed set of trusted
source documents, and makes it possible to *prove*, side by side, the difference between
a plain LLM answer and a retrieval-grounded one.

## 2. Use case

User asks a clinical/public-health question (e.g. "What should I know before taking
antibiotics?"). The system either:
- answers directly from the model's own knowledge (**RAG off**), or
- retrieves the most relevant chunks from the ingested PDFs, builds a context-grounded
  prompt, and answers from that context only (**RAG on**) — refusing to guess if the
  answer isn't in the knowledge base.

## 3. Objectives

1. Show a working application → API → LLM (Ollama/Code Llama) pipeline.
2. Build a real ingestion pipeline: documents → text extraction → chunking → embeddings → vector DB.
3. Implement real vector similarity retrieval and RAG, with a clear RAG vs non-RAG demo.
4. Split the pipeline into independently deployable services communicating over HTTP APIs.
5. Containerize every service and run the whole pipeline via Docker Compose / on AWS.

## 4. Technologies

| Concern | Choice | Why |
|---|---|---|
| LLM | Ollama + `codellama:7b-instruct-q4_K_M` | Assignment-mandated model; quantized instruct variant runs on CPU with ~8GB RAM |
| API framework | FastAPI | Async, typed, auto-generated OpenAPI docs |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) | Small (~90MB), fast on CPU, good quality/cost tradeoff |
| Vector DB | ChromaDB (persistent, local disk) | Zero-ops embedded vector store, good enough for a KB of a few thousand chunks |
| Frontend | Gradio | Minimal code for a usable chat UI with toggles/sliders |
| Containers | Docker + Docker Compose | Per-service isolation, service-name networking |
| Cloud | AWS EC2 (single instance) | Cheapest way to run Ollama's CPU inference off the student's Mac |

## 5. Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full diagrams. Summary:

```
Gradio Frontend → Application/Orchestration Service (app_service)
                        │                    │
                        ▼                    ▼
             Retrieval Service        LLM Service
             (embeds + searches)   (calls Ollama API)
                        │                    │
                        ▼                    ▼
                   ChromaDB              Ollama → Code Llama
```

## 6. Complete request flow

**Non-RAG:** `User → Frontend → app_service /chat → llm_service /generate → Ollama → Code Llama → answer`

**RAG:** `User → Frontend → app_service /chat → retrieval_service /retrieve (embed question →
vector search → top-k chunks + similarity + sources) → app_service builds grounded prompt →
llm_service /generate → Ollama → Code Llama → answer + sources + retrieved context`

## 7–12. Exercises 1–5

Fully documented, one section each, in [EXERCISES.md](EXERCISES.md).

## 13. Installation

Requires: Docker Desktop (Mac), Python 3.11+ only if you want to run something outside
Docker (e.g. tests). **You do not need to install Ollama, Code Llama, or any embedding
model locally** — everything heavy runs inside containers or on AWS.

```bash
git clone <this-repo>
cd IDT_PROJECT
cp .env.example .env      # [MAC] adjust values if needed
```

## 14. Mac development setup

**[MAC]** Everything below runs through Docker — nothing heavy touches your host Python.

```bash
docker compose build
docker compose up -d ollama            # start Ollama first
docker compose up ollama_pull          # pulls codellama (one-off, several GB — be patient)
docker compose up kb_ingest            # builds the vector index from ./docs (one-off)
docker compose up -d llm_service retrieval_service app_service frontend
```

Then open **http://localhost:7860** in your browser.

> Running Code Llama 7B via CPU-only Docker Desktop on a Mac is possible for a quick local
> smoke test, but is slow (30s-2min per answer) and uses several GB of RAM. For an actual
> demonstration/viva, run Ollama on AWS (below) and point `OLLAMA_URL` in `.env` at it —
> that's the intended architecture.

## 15. AWS setup

**[AWS]** Recommended: **one EC2 instance runs the entire stack** (simplest to explain in
a viva, cheapest to reason about billing for a single demo).

1. Launch an EC2 instance:
   - AMI: Ubuntu 22.04 LTS
   - Instance type: **`t3.xlarge`** (4 vCPU / 16 GB RAM) — gives headroom for Code Llama
     7B (~5-6GB resident) plus the other 3 containers. Budget alternative: `t3.large`
     (2 vCPU / 8 GB) works but is tighter — expect slower generations.
   - Storage: 30 GB gp3 (Code Llama's image is ~4-5GB; Docker images add a few more)
   - Security group: allow **inbound 22 (SSH, your IP only)** and **inbound 7860 (Gradio,
     your IP only or 0.0.0.0/0 only for the demo window)**. Do **not** open 8000, 8001, or
     11434 to the internet — those are internal, service-to-service ports reached only
     inside the Docker network.
2. **[AWS]** SSH in, install Docker + the Compose plugin, clone the repo, `cp .env.example .env`.
3. **[AWS]** Run the same commands as the Mac setup above (`docker compose build`, `up
   ollama`, `up ollama_pull`, `up kb_ingest`, `up -d llm_service retrieval_service
   app_service frontend`).
4. **[MAC]** Browse to `http://<ec2-public-ip>:7860` from your Mac — no AWS CLI, no local
   Ollama, no local model weights.

### Why CPU, not GPU

A quantized 7B model (`q4_K_M`, ~4-5GB) runs adequately on CPU for a single-user classroom
demo (tens of seconds per answer). A GPU instance (e.g. `g4dn.xlarge`, ~$0.53/hr) would
answer in 1-3 seconds but roughly **5x the hourly cost** for a benefit that doesn't matter
in a viva. Use GPU only if you specifically want to demonstrate GPU inference.

### AWS shutdown / cleanup procedure — do this every time you finish a session

```
[AWS] aws ec2 stop-instances --instance-ids <your-instance-id>
```
Stopping (not terminating) keeps your EBS volume (model weights, ingested KB) so next time
you only pay for storage (~$0.08/GB-month for gp3 — a 30GB volume is a few cents/month) and
can restart without re-pulling the model. **A running `t3.xlarge` costs ~$0.166/hr — a
forgotten instance running for a week costs ~$28.** When the project/course is fully done,
**terminate** the instance and delete the volume to stop even the storage charge.

## 16. Environment variables

See [.env.example](.env.example) for the full list: service URLs, `OLLAMA_MODEL`,
`CHUNK_SIZE`/`CHUNK_OVERLAP`, `TOP_K`, timeouts. Never commit a real `.env`.

## 17. Running services

`docker compose up -d` after the one-off `ollama_pull`/`kb_ingest` jobs have completed
once. Individual services can also be run outside Docker for development:
```bash
cd retrieval_service && pip install -r requirements.txt && uvicorn main:app --reload
```

## 18. Building the knowledge base

Add/replace PDFs or `.txt` files in `./docs`, then re-run ingestion (safe to re-run —
upserts by chunk ID):
```bash
docker compose up kb_ingest
```

## 19. Testing

**[MAC]** Tests are pure Python + mocked HTTP calls — no Docker, Ollama, or GPU required:
```bash
pip install -r tests/requirements.txt
pytest tests/ -v
```

## 20. RAG vs Non-RAG

In the Gradio UI, toggle **"Use RAG"** off/on and ask the same question. With RAG on, the
UI displays the mode banner, the retrieved chunks (with source filename, chunk id, and a
similarity score), and the list of source documents — proof retrieval genuinely happened.
See [EXERCISES.md](EXERCISES.md) Exercise 3 for a worked example.

## 21. Docker

Five Dockerfiles (`frontend`, `app_service`, `retrieval_service`, `llm_service`, plus the
pulled `ollama/ollama` image), orchestrated by [docker-compose.yml](docker-compose.yml).
Containers talk to each other by **service name** (`http://llm_service:8000`, never
`localhost`) over Compose's default network. Two one-off jobs (`ollama_pull`, `kb_ingest`)
prepare state (the model, the vector index) before the long-running services start.

## 22. API documentation

See [API.md](API.md). Each FastAPI service also serves interactive Swagger docs at
`/docs` (e.g. `http://localhost:8000/docs` for app_service).

## 23. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/chat` returns 502 "llm_service is unavailable" | Ollama hasn't finished pulling the model, or Ollama is down | Check `docker compose logs ollama_pull`; hit `llm_service`'s `/health` — `model_pulled` should be `true` |
| `/chat` with RAG on always says "not found in knowledge base" | `kb_ingest` never ran, or `./docs` was empty at ingest time | Run `docker compose up kb_ingest`, check its logs for "Indexed N chunks" |
| Frontend can't reach app_service | Wrong `APP_SERVICE_URL` (using `localhost` inside a container) | Must be the Compose service name, e.g. `http://app_service:8000` |
| First `/chat` call is very slow | Model + embedder loading lazily on first request (cold start) | Expected — subsequent calls are faster |
| `docker compose up` fails with ".env not found" | Forgot to copy the example env file | `cp .env.example .env` |

## 24. AWS shutdown procedure

See §15 above — always `stop` (or `terminate` at the end of the course) the EC2 instance
after a demo session.

## 25. Future improvements

- Swap the single-EC2 deployment for ECS Fargate + an Application Load Balancer if the
  assignment wants more distinct AWS services demonstrated.
- Add re-ranking after vector search for higher-precision retrieval.
- Stream tokens from Ollama (`stream: true`) to the frontend instead of waiting for the
  full completion.
- Add authentication in front of the public Gradio URL before leaving it open longer term.
