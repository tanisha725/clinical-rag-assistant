from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_rag: bool = True
    top_k: int = Field(default=3, ge=1, le=20)


class SourceChunk(BaseModel):
    text: str
    source: str
    chunk_id: int
    similarity: float


class ChatResponse(BaseModel):
    answer: str
    used_rag: bool
    top_k: int
    sources: list[str] = []
    retrieved_context: list[SourceChunk] = []
    model: str | None = None
