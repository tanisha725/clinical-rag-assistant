import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from config import DEFAULT_TOP_K
from embeddings import embed_text
from vector_store import count, query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retrieval_service")

app = FastAPI(title="Retrieval Service", description="Query embedding + vector similarity search over the clinical knowledge base.")


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=20)


class RetrievedChunk(BaseModel):
    text: str
    source: str
    chunk_id: int
    similarity: float


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]
    knowledge_base_size: int


@app.get("/health")
def health():
    return {"status": "ok", "knowledge_base_size": count()}


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest):
    logger.info("Retrieval request: top_k=%d question=%r", req.top_k, req.question[:80])

    kb_size = count()
    if kb_size == 0:
        logger.warning("Knowledge base is empty — returning no chunks.")
        return RetrieveResponse(chunks=[], knowledge_base_size=0)

    embedding = embed_text(req.question)
    results = query(embedding, req.top_k)

    chunks = [
        RetrievedChunk(
            text=doc,
            source=meta.get("source", "unknown"),
            chunk_id=meta.get("chunk_id", -1),
            # Chroma's default space is L2 distance (smaller = more similar).
            # Convert to a bounded 0-1 "similarity" so the frontend can show
            # something intuitive without leaking distance-metric internals.
            similarity=1.0 / (1.0 + dist),
        )
        for doc, meta, dist in zip(results["documents"], results["metadatas"], results["distances"])
    ]
    logger.info("Retrieved %d chunks", len(chunks))
    return RetrieveResponse(chunks=chunks, knowledge_base_size=kb_size)
