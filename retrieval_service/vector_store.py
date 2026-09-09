from functools import lru_cache

import chromadb

from config import COLLECTION_NAME, VECTOR_DB_PATH


@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    return client.get_or_create_collection(COLLECTION_NAME)


def add_chunks(ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]) -> None:
    # upsert (not add) so re-running ingestion on unchanged docs is idempotent
    # instead of erroring on duplicate IDs.
    get_collection().upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def query(query_embedding: list[float], top_k: int) -> dict:
    collection = get_collection()
    if collection.count() == 0:
        return {"documents": [], "metadatas": [], "distances": []}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return {
        "documents": results["documents"][0],
        "metadatas": results["metadatas"][0],
        "distances": results["distances"][0],
    }


def count() -> int:
    return get_collection().count()
