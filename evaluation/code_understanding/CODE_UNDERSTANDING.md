# Exercise 6 — Repository / Codebase Understanding

## Setup

The production knowledge base (`clinical_docs`, the CDC PDFs) is documents, not code — so
it cannot directly test multi-file code understanding. Rather than skip this exercise or
write a purely theoretical answer, a **second, separate ChromaDB collection** (`code_kb`)
was built from this project's own 19 Python source files (`app_service`, `retrieval_service`,
`llm_service`, `frontend`, `tests`), using the same embedding model
(`all-MiniLM-L6-v2`) and the same retrieve→context→generate pattern as the main app, but
completely isolated from the production `clinical_docs` collection — nothing here touches
or affects the deployed app. See `code_kb_ingest.py` and `code_query.py`.

Chunking: one chunk per file (every file in this project is under ~150 lines, so a
per-file chunk keeps a function's full context together rather than splitting mid-function).
Model used: `qwen2.5:0.5b-instruct` (the only model that runs at practical speed on this
hardware — see `../ANALYSIS.md`). Top-k = 3 file chunks per question.

Since I (the person who wrote this codebase) know the actual ground truth for every
question, grading here doesn't require guessing — it's verifiable against the real code.

## Results: QUESTION → RETRIEVED FILES → ANSWER

Full raw data in `code_understanding_results.json`. Summary and grading:

| ID | Question | Retrieved top-3 (similarity) | Correct file retrieved? | Answer quality | Correctness |
|---|---|---|---|---|---|
| C01 | Which service calls llm_service? | llm_service/main.py, app_service/config.py, **app_service/main.py** | Partial — missed `orchestrator.py` (the actual caller) | Vague, tautological ("calls the llm_service service"), never names app_service or cites `_call_llm` | 0-1 |
| C02 | Which file does vector similarity search? | ingest.py, test_retrieval_service.py, **vector_store.py** | Yes (3rd of 3) | Correct, concise | 2 |
| C03 | What happens after app_service receives a chat request? | **app_service/main.py**, **orchestrator.py**, frontend/main.py | Yes, both key files retrieved | Weak — just outputs a filename, doesn't trace the RAG-on/off branching | 1 |
| C04 | Which component builds the RAG prompt? | llm_service/main.py, **orchestrator.py**, llm_service/config.py | Yes (2nd of 3, lower similarity) | Correctly identifies orchestrator.py despite it not being top-1; minor fabricated merged path | 2 |
| C05 | Which files chunk documents for the KB? | config.py, **ingest.py**, **chunking.py** | Yes, both | Partial — answer only echoes config.py + ingest.py, omits chunking.py from the final answer | 1 |
| C06 | Which test file covers retrieval_service? | **test_retrieval_service.py**, conftest.py, ingest.py | Yes (top-1) | Correct, precise | 2 |
| C07 | What's affected if chunk_text() is modified? | **chunking.py**, **test_chunking.py**, config.py | Yes, both key files | **Wrong** — circular/nonsensical answer ("not affected by any modifications to itself"), fails to reason about downstream dependents | 0 |
| C08 | Which module loads the embedding model? | **embeddings.py**, config.py, vector_store.py | Yes (top-1) | Correct, cites real code | 2 |
| C09 | Which file defines the Ollama client? | llm_service/main.py, **ollama_client.py**, config.py | Yes (2nd of 3) | Correct, concise | 2 |
| C10 | Which service owns the Gradio UI? | **frontend/main.py**, app_service/main.py, config.py | Yes (top-1) | Correct, cites real code | 2 |

**Retrieval hit rate**: 9/10 questions retrieved the actual ground-truth file within top-3
(the one clear miss, C01, never surfaced `orchestrator.py` at all — its embedding
similarity to "which service calls llm_service" was apparently lower than `app_service`'s
other, less relevant files).

**Answer correctness**: 6/10 fully correct, 3/10 partially correct, 1/10 wrong. Average
score 1.5/2.

## The pattern: lookup vs. relationship reasoning

A clear split emerges between two question types:

- **"Which file/module does X?"** (C02, C06, C08, C09, C10) — single-file identification.
  The system does this well: correct file retrieved and correctly named in 5/5 of these.
- **"What happens when...?" / "What would be affected if...?"** (C01, C03, C07) — questions
  requiring the model to trace a *sequence* across files or reason about *downstream
  dependents*, not just identify one file. The system struggled here: C07 (impact analysis)
  failed outright, and C01/C03 (flow tracing) retrieved the right files but produced weak,
  non-explanatory answers.

This matches exactly what the assignment brief anticipates for repository-level
understanding: a RAG system built on flat per-file chunk retrieval and cosine similarity
has no explicit model of *call relationships* (who calls whom) or *dependency graphs*
(what depends on what) — it can only surface files whose *text* is semantically similar to
the question. "What does file X do" is a text-similarity problem RAG handles natively.
"What would break if I change function Y" is a *graph traversal* problem — which is
precisely the gap that tools like Sourcegraph (mentioned in the assignment as next week's
topic) are built to close via actual call-graph/reference indexing rather than embedding
similarity.

## Viva explanation

"I tested whether our RAG pipeline, unmodified in mechanism, could answer questions about
its own multi-file codebase by building a second knowledge base from our own source files.
It's genuinely good at 'which file does X' — that's just semantic search working as
intended. It's weak at 'what happens after X' and outright fails at 'what would break if I
changed X' — those need to know *which functions call which*, and nothing in a vector
database captures that; it only knows which chunks of text read similarly to the question.
That's the concrete limitation this exercise was designed to expose."
