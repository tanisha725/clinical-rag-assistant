# Evaluation Metrics — Definitions

This document defines exactly how each metric required by Exercise 3 is calculated for
this project. All metrics are computed per (model, question) pair, then averaged per
model for the summary table in `results/summary.csv`.

## Quality metrics

### Correctness / Accuracy
**Manual rubric, scored 0-2 per answer**, graded against the `ground_truth_keyfacts` list
in `questions.json` (facts extracted directly from the source PDFs):
- **2** — answer states the key facts correctly and does not contradict the source.
- **1** — answer is partially correct: some key facts present, some missing, or a minor
  inaccuracy that doesn't change the clinical meaning.
- **0** — answer is wrong, contradicts the source, or (for `out_of_kb` questions) confidently
  invents an answer instead of declining.

This is manual rather than automated because verifying whether a clinical claim is
factually correct requires comparing it to the actual PDF content, not just string/keyword
matching — an automated keyword check would falsely reward an answer that mentions the
right words in a wrong or nonsensical claim.

### Relevance
**Manual rubric, scored 0-1 per answer**: does the answer actually address what was asked
(regardless of factual correctness)?
- **1** — on-topic, responds to the actual question.
- **0** — off-topic, answers a different question, or is mostly filler/refusal when the
  question was in fact answerable.

### Retrieval Quality
**Manual + automated, only for `in_kb` questions**: for each question, checked whether the
chunks retrieved by `retrieval_service` (recorded per model run — retrieval is the same
regardless of which LLM is used, but is re-verified per run to catch anything that changed)
actually contain the source sentence(s) needed to answer the question. Scored 0-1:
- **1** — at least one retrieved chunk contains the necessary supporting fact(s).
- **0** — none of the retrieved chunks contain the necessary fact (a retrieval miss, not an
  LLM failure — this is what Exercise 5 analyzes in depth).

Also reported: **average similarity score** (from `retrieval_service`'s
`1/(1+distance)` conversion) across retrieved chunks per question, as a continuous signal
alongside the binary hit/miss.

### Hallucination Rate
**Manual rubric, per model**: percentage of answers (across all questions) where the model
stated a specific fact (a number, a named drug, a named condition, a causal claim) that is
**not present in the retrieved context and not present in the source PDFs at all** — i.e.
fabricated, not just imprecise. Calculated as:

```
hallucination_rate = (# answers with at least one fabricated claim) / (total # answers) × 100%
```

Distinguished from "incorrect" (Correctness=0 for a *retrieval miss or misreading* of real
content) — hallucination specifically means the model invented something with no basis in
any source document.

### Test-Pass Rate for generated code
**Not applicable** to this application. The Clinical RAG Assistant is a document Q&A
system, not a code-generation tool — none of the 29 evaluation questions ask a model to
produce executable code, so there is nothing to unit-test. This is called out explicitly
rather than silently omitted, per the assignment's "wherever applicable" instruction.
(Exercise 6's code-repository-understanding task uses a *separate*, code-specific
evaluation — see `code_understanding/` — but even there the task is Q&A about code, not
code generation, so a test-pass rate still doesn't apply.)

## Performance metrics

### Response Latency
Wall-clock seconds from sending the prompt to Ollama's `/api/generate` to receiving the
full (non-streamed) response, read directly from Ollama's own `total_duration` field in
its response (nanoseconds, converted to seconds) — this is more accurate than timing the
HTTP round-trip in the eval script, since it excludes network/eval-script overhead and
reflects actual model inference time.

### Token Usage
Read directly from Ollama's response: `prompt_eval_count` (tokens in the input prompt,
including the RAG context when applicable) and `eval_count` (tokens generated in the
response). Reported separately and as a sum per question, then averaged per model.

### CPU / Memory Consumption
Sampled via `docker stats --no-stream ollama_smoketest` **every 0.5s for the duration of
each generation call**, run from a background thread (`resource_monitor.py`) started just
before the request and stopped just after. Reported per question as **peak** and
**average** CPU% and memory (MiB) across all samples taken during that call, then averaged
per model across all 29 questions. GPU is not measured — this deployment runs entirely on
CPU (see README.md/ARCHITECTURE.md for why), so a GPU metric would read zero for every
model and add no information.
