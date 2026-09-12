# ANALYSIS.md — Exercises 1-4: Multi-Model Evaluation

## Exercise 1 — models evaluated, and an honest note on what actually ran

Per the assignment, the same application, same prompts, same 29 questions, and same
knowledge base (`../docs/`, 6 CDC PDFs, `clinical_docs` ChromaDB collection) were held
constant across three models. Chosen to fit this application's actual domain (clinical
Q&A, not code) rather than the assignment's code-specific examples — see the note on model
substitution below:

| Label | Model | Role in comparison |
|---|---|---|
| `qwen25_0.5b` | `qwen2.5:0.5b-instruct` (~400MB) | General-purpose small model |
| `codellama_stub` | `qwen2.5-coder:1.5b-instruct` (~1GB) | **Disclosed stand-in for Code Llama** — real Code Llama (7B minimum) cannot run on this free-tier hardware at all; this is the smallest genuinely code-oriented model that could be pulled |
| `llama32_1b` | `llama3.2:1b-instruct-q4_K_M` (~800MB) | General-purpose small model, different family from Qwen |

**What actually happened**: `qwen25_0.5b` completed the full 29-question run successfully.
**`codellama_stub` and `llama32_1b` could not complete a single generation within any
practical timeout** — see below. This was not expected going in; it was discovered during
the evaluation itself, and is reported as a primary finding rather than worked around.

## Exercise 2 — the evaluation dataset

29 questions in `questions.json`, adapted from the assignment's code-QA categories to this
app's actual clinical-QA domain: `explanation` (5), `retrieval` (6), `synthesis` (3),
`risk_analysis` (4), `generation` (4), `improvement` (2), `rag_grounded` (2), `out_of_kb`
(3, deliberately not covered by the KB, to test refusal behavior). Every in-KB question
carries `ground_truth_keyfacts` extracted directly from the source PDFs, so grading is
against verifiable facts, not the grader's memory.

## Exercise 3 — quantitative results

See `metrics.md` for exactly how each metric is calculated, and `results/summary.csv` for
the full table. Headline numbers:

| Metric | qwen2.5:0.5b-instruct | qwen2.5-coder:1.5b (Code Llama stand-in) | llama3.2:1b |
|---|---|---|---|
| Questions completed | 29/29 | 0/29 (1 calibration sample) | 0/29 (1 calibration sample) |
| Avg correctness (0-2) | 1.03 | n/a | n/a |
| Avg relevance (0-1) | 0.90 | n/a | n/a |
| Hallucination rate | 31.0% | n/a | n/a |
| Avg latency | 32.4s | 326.7s (single sample) | 575.9s (single sample) |
| Tokens/second | 3.46 | **0.05** | **0.08** |
| Avg prompt/completion tokens | 1208 / 112 | 38 / 11 | 34 / 43 |
| Model load time | ~2s (warm) | 65.3s | 40.4s |
| Avg CPU % during generation | 59.6% | 17.9% | not separately measured |
| Avg memory | 430 MiB | 531 MiB | not separately measured |

**Test-Pass Rate for generated code**: not applicable — this app is a document Q&A system,
none of the 29 questions ask for executable code (see `metrics.md` for why this is called
out explicitly rather than silently skipped).

## Why the two larger models are reported as "infeasible," not just "slow"

`codellama_stub` and `llama32_1b` were each given a full 500-second timeout per question in
the main harness — every one of the 29 questions timed out. To rule out the app's own
overhead as the cause, both models were also tested **in isolation** (`ollama run` directly
inside the Ollama container, every other service — frontend, app_service, retrieval_service
— stopped, so the model had the entire 914MB box to itself):

- `qwen2.5-coder:1.5b-instruct`: **0.05 tokens/second** (11 tokens took 3m52s of generation
  alone, plus 65s just to load the model into memory). CPU usage during this averaged only
  17.9% — meaning the bottleneck was disk I/O from swap thrashing, not compute.
- `llama3.2:1b-instruct-q4_K_M`: **0.08 tokens/second** (43 tokens took 8m31s).

Both numbers are 40-70x slower than `qwen2.5:0.5b-instruct`'s measured 3.46 tokens/second,
despite `qwen2.5:0.5b` being run *without* isolating other services — i.e., under *more*
memory pressure, not less. The conclusion is unambiguous: on a 1GB-RAM box, a model whose
weights exceed roughly ~400-500MB does not merely run slower, it crosses a cliff into
being functionally unusable, because it no longer fits in available RAM alongside its own
KV cache and gets paged to disk continuously.

## Exercise 4 — analysis

**Which model provides better accuracy?** Only one model produced a usable dataset to
measure this on. Within `qwen2.5:0.5b`'s own results, accuracy was middling
(avg correctness 1.03/2, i.e. roughly "half-correct" on average) — see `RAG_PIPELINE_ANALYSIS.md`
for concrete hallucination and refusal-failure examples. No comparative accuracy claim
between models can be made responsibly, because the other two never produced enough output
to grade.

**Which model produces fewer hallucinations?** Unanswerable for the same reason — a
31.0% hallucination rate is only known for `qwen2.5:0.5b`. What *can* be said: producing
zero usable output (as the other two effectively did) is not "zero hallucinations" in any
meaningful sense — a model that cannot answer is not a safer model, it's a non-functional one
for this deployment target.

**Which model has lower response latency / requires fewer resources?**
`qwen2.5:0.5b-instruct` decisively, by 40-70x, on both counts. This is the one comparison
this evaluation answers with full confidence.

**Is the most accurate model also the most efficient?** By elimination, yes — since it's
the only model that produced a gradable output at all on this hardware, it is trivially
also the most "efficient" by every measured metric. This isn't a meaningful trade-off
finding so much as a hardware ceiling finding.

**Is there a quality-latency-resource trade-off?** Yes, but not the graceful kind the
assignment's own example describes ("Model A is more accurate but slower; Model B is
almost as accurate but much faster"). What was found instead is a **cliff, not a slope**:
below a certain model size for a given amount of RAM, latency doesn't degrade
proportionally with model size — it degrades catastrophically (3.46 tok/s → 0.05-0.08
tok/s, not a 2-3x slowdown but a 40-70x one) once the model's resident memory exceeds what
physically fits without swapping. The practical lesson for anyone deploying an LLM on
constrained hardware: **size the model to the RAM budget with real headroom, not just
"does the download fit on disk"** — a model that fits on disk can still be completely
non-functional once it has to run.

## What this means for the assignment's actual question

*"How does the choice of LLM affect the performance of the same application?"* — On this
specific memory-constrained free-tier deployment, LLM choice is not primarily a
quality/style trade-off (which was the expected framing); it is a **binary functional/
non-functional threshold** determined almost entirely by resident memory footprint versus
available RAM. Model architecture, training data, or code-specialization mattered far less
in this environment than whether the model's weights fit the box. On less constrained
hardware (the `t3.large`+ tier documented in the main README), this ceiling would not
exist and the comparison would likely surface the quality-focused trade-offs the assignment
anticipates — that comparison was outside this evaluation's (deliberately free-tier) scope.
