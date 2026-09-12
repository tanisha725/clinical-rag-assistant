import logging

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import OLLAMA_MODEL, OLLAMA_URL
from ollama_client import OllamaError, generate_raw

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm_service")

app = FastAPI(title="LLM Service", description="Wraps Ollama's API and serves Code Llama completions.")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class GenerateResponse(BaseModel):
    answer: str
    model: str
    # Metadata for the model-comparison evaluation (evaluation/); not used by the
    # frontend, but harmless additive fields on the existing response contract.
    latency_seconds: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@app.get("/health")
def health():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        model_ready = OLLAMA_MODEL in models
        return {
            "status": "ok" if model_ready else "degraded",
            "ollama_reachable": True,
            "model": OLLAMA_MODEL,
            "model_pulled": model_ready,
            "available_models": models,
        }
    except requests.exceptions.RequestException as exc:
        return {"status": "degraded", "ollama_reachable": False, "model": OLLAMA_MODEL, "error": str(exc)}


@app.post("/generate", response_model=GenerateResponse)
def generate_endpoint(req: GenerateRequest):
    logger.info("Generate request, prompt length=%d chars", len(req.prompt))
    try:
        raw = generate_raw(req.prompt)
    except OllamaError as exc:
        logger.error("Ollama call failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    answer = raw["response"]
    logger.info("Generation complete, answer length=%d chars", len(answer))
    return GenerateResponse(
        answer=answer,
        model=OLLAMA_MODEL,
        latency_seconds=raw.get("total_duration", 0) / 1e9 if raw.get("total_duration") else None,
        prompt_tokens=raw.get("prompt_eval_count"),
        completion_tokens=raw.get("eval_count"),
    )
