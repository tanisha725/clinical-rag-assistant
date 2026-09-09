from functools import lru_cache

from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    # Loaded once per process and cached: model load is the expensive part,
    # not the per-call encode.
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    return get_embedder().encode(text).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts).tolist()
