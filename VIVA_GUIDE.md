# VIVA_GUIDE.md

Quick-reference for defending this project live. Each answer is short on purpose — expand
with the referenced doc if the examiner wants more depth.

## "Walk me through what happens when I ask a question."

RAG on: question → Gradio sends it to `app_service /chat` → `app_service` calls
`retrieval_service /retrieve`, which embeds the question with the same model used at
ingestion and does a ChromaDB nearest-neighbor search → the top-k chunks (with source and
similarity) come back → `app_service` builds a prompt telling Code Llama to answer only
from that context → sends it to `llm_service /generate` → `llm_service` calls Ollama's
`/api/generate` → the answer, sources, and retrieved chunks flow back to the UI.

RAG off: the question skips retrieval entirely and goes straight to `llm_service`.

(Full sequence diagrams: ARCHITECTURE.md.)

## "Is the live demo actually running Code Llama?"

Be direct if asked this: **no, not on the current free-tier box.** The documented,
required architecture uses `codellama:7b-instruct-q4_K_M` (see `.env.example`,
`docker-compose.yml`, and every other section of this guide) — that's the actual answer
to "what model does this project use." The live free-tier instance runs a much smaller
substitute (`qwen2.5:0.5b-instruct`, ~400MB) in a standalone container kept deliberately
outside the versioned compose files, purely so retrieval/RAG mechanics can be demoed with
a real generated answer instead of a 502, since a 1GB instance physically cannot run Code
Llama. State plainly that satisfying the requirement for real needs a bigger instance
(README.md §15, ~$0.08/hr, a few cents for a session) and that the swap is a one-line
`.env` change (`OLLAMA_MODEL`/`OLLAMA_URL`) — do not imply the small model meets the
requirement.

## "Why Code Llama specifically, and why that tag?"

The assignment requires Code Llama via Ollama. We use
`codellama:7b-instruct-q4_K_M` — the instruct-tuned variant (follows the "answer only
from context" instruction far better than the base completion model) at 4-bit
quantization (~4-5GB), which runs on CPU with ~8GB RAM. A smaller model like
`llama3.2:1b` would run faster but doesn't satisfy the assignment's explicit requirement.

## "Why does the LLM run on AWS and not your laptop?"

CPU inference for a 7B model needs real RAM and sustained CPU — running it constantly on
a MacBook alongside normal development work isn't practical, and it's not how a real
deployment would look either. We put Ollama (and the whole stack) on a single AWS EC2
instance so the Mac only needs a browser. See README.md §15 for the exact instance type
and cost reasoning, and the shutdown procedure so it isn't left running (billing) between
demos.

## "Prove retrieval is actually happening, not faked."

Toggle "Use RAG" off, ask a question, note the answer and the "RAG OFF" banner (no
sources shown). Toggle it on, ask the *same* question — the UI now shows a "RAG ON"
banner, the retrieved chunks with a similarity score and originating PDF filename for
each, and the answer changes to only use facts traceable to those chunks. Ask something
not covered by any of the 6 PDFs with RAG on — the answer should explicitly say it wasn't
found in the knowledge base, rather than guessing.

## "What's your chunking strategy and why those numbers?"

Word-count sliding window, 500 words per chunk with a 50-word (10%) overlap. 500 words
keeps a full clinical instruction/paragraph together without ballooning the prompt when
several chunks are retrieved at once; the overlap stops a sentence that straddles a
boundary from losing meaning on either side. Both are environment variables
(`CHUNK_SIZE`, `CHUNK_OVERLAP`), not hardcoded — tunable without a code change.
(EXERCISES.md Exercise 2.)

## "What embedding model, and why?"

`sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions. Small (~90MB), fast enough for
CPU-only encoding of both the ~150-200 knowledge-base chunks and each incoming query,
good semantic-similarity quality for short passages — no need for a heavier embedding
model on a knowledge base this size.

## "What's your vector database and how does similarity search work?"

ChromaDB, persistent on disk (a Docker volume in production). Each chunk is stored with
its embedding plus metadata (`source`, `doc_id`, `chunk_id`). A query embeds the question
with the same model, then ChromaDB returns the k nearest vectors by L2 distance; we
convert that distance to a bounded 0-1 "similarity" score for display.

## "How are the services separated, and why?"

Four services, one job each: `frontend` (UI only), `app_service` (orchestration —
decides RAG vs not, calls the other two, merges results), `retrieval_service` (embedding
+ vector search, owns the knowledge base), `llm_service` (the only thing that talks to
Ollama). They only know each other's HTTP APIs, not each other's internals — any one can
be redeployed, scaled, or replaced independently. (EXERCISES.md Exercise 4.)

## "What happens if a service goes down?"

Every outbound call has a timeout and explicit error handling. If `retrieval_service` or
`llm_service` is unreachable, `app_service` returns HTTP 502 naming which service failed,
instead of hanging or crashing with a stack trace. `llm_service /health` even reports
whether Ollama is reachable *and* whether the Code Llama tag has actually been pulled.

## "Show me the Docker setup."

`docker-compose.yml` — five long-running services plus two one-off jobs (`ollama_pull`,
`kb_ingest`) gated with `service_completed_successfully` so nothing starts before its
dependencies are ready. Every inter-container URL uses the Compose service name, never
`localhost` — that was the single most severe bug in the original codebase (a
service-to-service call that could never have worked under Docker). See
PROJECT_AUDIT.md §13/§16 for exactly what was wrong before, and how it was fixed.

## "How much does running this on AWS cost, and how do you avoid waste?"

A `t3.xlarge` (16GB RAM, enough headroom for the model plus the other 3 containers)
costs roughly $0.166/hr on-demand. We stop (not terminate) the instance after every demo
session — stopped instances only bill for EBS storage (a few cents/month for 30GB) — and
terminate it entirely once the course is finished. Exact commands are in README.md §15/§24.

## "What would you improve given more time?"

Streaming token-by-token responses from Ollama instead of waiting for the full
completion; re-ranking retrieved chunks for higher precision; moving from a single EC2
instance to ECS Fargate if more distinct AWS services need to be demonstrated. (Full list:
README.md §25.)
