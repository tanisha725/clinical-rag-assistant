import logging

import requests

from config import (
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_SERVICE_URL,
    REQUEST_TIMEOUT_SECONDS,
    RETRIEVAL_SERVICE_URL,
)
from models import ChatResponse, SourceChunk

logger = logging.getLogger("app_service.orchestrator")

RAG_SYSTEM_PROMPT = """You are a clinical information assistant. Answer the \
question using ONLY the context below. Do not invent facts, statistics, or \
sources that are not present in the context. If the context does not \
contain enough information to answer, respond exactly with: \
"I could not find this information in the available knowledge base." \
Do not use outside/prior knowledge to fill gaps.

Context:
{context}

Question: {question}

Answer:"""


class UpstreamServiceError(Exception):
    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"{service} error: {detail}")


def _call_retrieval(question: str, top_k: int) -> list[SourceChunk]:
    try:
        r = requests.post(
            f"{RETRIEVAL_SERVICE_URL}/retrieve",
            json={"question": question, "top_k": top_k},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise UpstreamServiceError("retrieval_service", str(exc)) from exc

    body = r.json()
    return [SourceChunk(**chunk) for chunk in body.get("chunks", [])]


def _call_llm(prompt: str) -> str:
    try:
        r = requests.post(
            f"{LLM_SERVICE_URL}/generate",
            json={"prompt": prompt},
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise UpstreamServiceError("llm_service", str(exc)) from exc

    return r.json()["answer"]


def handle_chat(message: str, use_rag: bool, top_k: int) -> ChatResponse:
    if not use_rag:
        logger.info("RAG disabled — sending question directly to the LLM.")
        answer = _call_llm(message)
        return ChatResponse(answer=answer, used_rag=False, top_k=top_k)

    logger.info("RAG enabled — retrieving top_k=%d chunks.", top_k)
    chunks = _call_retrieval(message, top_k)
    logger.info("Retrieved %d chunks for context.", len(chunks))

    if not chunks:
        context = "(no relevant documents found in the knowledge base)"
    else:
        context = "\n\n".join(f"[{c.source}] {c.text}" for c in chunks)

    prompt = RAG_SYSTEM_PROMPT.format(context=context, question=message)
    answer = _call_llm(prompt)

    sources = sorted({c.source for c in chunks})
    return ChatResponse(
        answer=answer,
        used_rag=True,
        top_k=top_k,
        sources=sources,
        retrieved_context=chunks,
    )
