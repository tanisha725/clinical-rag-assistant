# Evaluation — Multi-Model Assessment of the Clinical RAG Assistant

This directory is a continuation of the Clinical RAG Assistant (see the root `README.md`,
`ARCHITECTURE.md`, `EXERCISES.md`) — it does not build a new application. It evaluates the
same app, same RAG pipeline, same knowledge base, against three different LLM models and
analyzes the results, per this week's assignment.

## Map: assignment exercises → files in this directory

| Exercise | What it asked for | Where it is |
|---|---|---|
| 1 — Evaluate multiple LLM models | Same app/prompts/questions/KB across 3+ models | `ANALYSIS.md` §Exercise 1, `results/summary.csv` |
| 2 — Evaluation dataset | 20-30 representative questions | `questions.json` |
| 3 — Quantitative evaluation | All required quality + performance metrics, with method defined | `metrics.md` (definitions), `results/summary.csv` (values), `results/raw/<model>/` (per-question raw data) |
| 4 — Analyze the results | Go beyond a table; answer the trade-off questions | `ANALYSIS.md` §Exercise 4 |
| 5 — Analyze the RAG pipeline | QUESTION→CONTEXT→RESPONSE traces, retrieval/context/response quality chain | `RAG_PIPELINE_ANALYSIS.md` |
| 6 — Repository/codebase understanding | Test multi-file reasoning against your own codebase | `code_understanding/CODE_UNDERSTANDING.md` |

## How to reproduce

- `run_eval.py` — runs the 29-question set against whichever model `llm_service` is
  currently configured with, through the real, unmodified `app_service /chat` API (RAG
  always on). Run on the EC2 host: `python3 run_eval.py --model-label <name>`.
- `run_all_models.sh` — switches `OLLAMA_MODEL` in `.env`, restarts `llm_service`, and runs
  `run_eval.py` for each of the 3 models in turn. In practice, two of the three models
  needed to be tested with a separate isolated calibration method instead — see
  `results/calibration_tests.md` and `ANALYSIS.md` for why.
- `resource_monitor.py` — samples `docker stats` on the Ollama container throughout each
  generation call, used by `run_eval.py`.
- `code_understanding/code_kb_ingest.py` + `code_query.py` — Exercise 6's separate code
  knowledge base and query harness, run inside the `retrieval_service` container (already
  has the embedding model installed).

## Headline finding

Only `qwen2.5:0.5b-instruct` could actually run at usable speed on the free-tier hardware
this project deploys to. The other two candidates — `qwen2.5-coder:1.5b-instruct` (used as
a disclosed Code Llama stand-in, since real Code Llama cannot run on this hardware at all)
and `llama3.2:1b-instruct-q4_K_M` — were empirically measured at 0.05 and 0.08
tokens/second respectively (40-70x slower than the working model), making them functionally
unusable rather than merely slower. This was not an assumption going in — it was discovered
and rigorously measured during the evaluation, and is reported as this evaluation's primary
finding rather than worked around. Full detail in `ANALYSIS.md`.
