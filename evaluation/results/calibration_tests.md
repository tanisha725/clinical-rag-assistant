# Calibration tests — raw evidence for the "infeasible" finding

Both larger models timed out on every one of the 29 main-harness questions (500s timeout
each). Before concluding infeasibility, each was tested in isolation: `ollama run`
directly against the Ollama container via its CLI (bypasses the app entirely), with
`frontend`, `app_service`, `retrieval_service`, and `llm_service` all stopped so the model
had the full 914MB box to itself and zero competition for memory. Prompt: "What is TB?
Answer in one sentence."

## qwen2.5-coder:1.5b-instruct (Code Llama stand-in)

```
$ time docker exec ollama_smoketest ollama run qwen2.5-coder:1.5b-instruct \
    "What is TB? Answer in one sentence." --verbose

TB is a lung infection caused by bacteria.

total duration:       5m26.700644555s
load duration:        1m5.267852813s
prompt eval count:    38 token(s)
prompt eval duration: 28.754526s
prompt eval rate:     1.32 tokens/s
eval count:           11 token(s)
eval duration:        3m51.862814s
eval rate:            0.05 tokens/s

real    5m28.614s
```

11 tokens of output took 3m52s to generate. Model load alone took 65s.

## llama3.2:1b-instruct-q4_K_M

```
$ time docker exec ollama_smoketest ollama run llama3.2:1b-instruct-q4_K_M \
    "What is TB? Answer in one sentence." --verbose

...tuberculosis... lung infection caused by bacteria..., and brain.

total duration:       9m35.859613541s
load duration:        40.393679997s
prompt eval count:    34 token(s)
prompt eval duration: 24.116325s
prompt eval rate:     1.41 tokens/s
eval count:           43 token(s)
eval duration:        8m31.123307s
eval rate:            0.08 tokens/s

real    9m37.670s
```

43 tokens took 8m31s. Even worse than the coder model despite a smaller file size (807MB
vs ~1GB), likely because a larger default context window was allocated for it.

## For comparison: qwen2.5:0.5b-instruct, same box, NOT isolated (other services still running)

From the full 29-question run (`results/raw/qwen25_0.5b/`), e.g. Q01: 127 completion
tokens in 48.8s wall-clock ≈ **2.6 tokens/second**, running *alongside* frontend,
app_service, and retrieval_service competing for the same 914MB — i.e., under objectively
worse conditions than the isolated tests above, and still 30-50x faster.
