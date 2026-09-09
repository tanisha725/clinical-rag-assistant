import logging

import requests
from fastapi import FastAPI, HTTPException

from config import LLM_SERVICE_URL, RETRIEVAL_SERVICE_URL
from models import ChatRequest, ChatResponse
from services.orchestrator import UpstreamServiceError, handle_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("app_service")

app = FastAPI(
    title="Application / Orchestration Service",
    description="Receives chat requests, orchestrates retrieval + LLM calls, returns the final answer.",
)


@app.get("/health")
def health():
    downstream = {}
    for name, url in [("retrieval_service", RETRIEVAL_SERVICE_URL), ("llm_service", LLM_SERVICE_URL)]:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            downstream[name] = r.json()
        except requests.exceptions.RequestException as exc:
            downstream[name] = {"status": "unreachable", "error": str(exc)}
    return {"status": "ok", "downstream": downstream}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    logger.info("Chat request received: use_rag=%s top_k=%d", req.use_rag, req.top_k)
    try:
        return handle_chat(req.message, req.use_rag, req.top_k)
    except UpstreamServiceError as exc:
        logger.error("Upstream failure: %s", exc)
        raise HTTPException(status_code=502, detail=f"{exc.service} is unavailable: {exc.detail}")
