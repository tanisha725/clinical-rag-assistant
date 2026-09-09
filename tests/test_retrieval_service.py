import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ROOT, "retrieval_service")


@pytest.fixture
def client(monkeypatch):
    """Import retrieval_service.main with embeddings/vector_store stubbed out,
    so the test never needs sentence-transformers or chromadb installed."""
    for name in ("config", "main", "embeddings", "vector_store", "chunking"):
        sys.modules.pop(name, None)

    fake_embeddings = type(sys)("embeddings")
    fake_embeddings.embed_text = lambda text: [0.1, 0.2, 0.3]
    fake_embeddings.embed_texts = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
    fake_embeddings.get_embedder = lambda: None
    sys.modules["embeddings"] = fake_embeddings

    fake_vector_store = type(sys)("vector_store")
    fake_vector_store.count = lambda: 2
    fake_vector_store.query = lambda embedding, top_k: {
        "documents": ["Take antibiotics exactly as prescribed.", "Finish the full course."],
        "metadatas": [{"source": "abx.pdf", "chunk_id": 0}, {"source": "abx.pdf", "chunk_id": 1}],
        "distances": [0.1, 0.4],
    }
    sys.modules["vector_store"] = fake_vector_store

    original_path = list(sys.path)
    sys.path.insert(0, SERVICE_DIR)
    import main as retrieval_main

    yield TestClient(retrieval_main.app)

    sys.path = original_path
    for name in ("config", "main", "embeddings", "vector_store", "chunking"):
        sys.modules.pop(name, None)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["knowledge_base_size"] == 2


def test_retrieve_returns_chunks_with_similarity_and_source(client):
    r = client.post("/retrieve", json={"question": "How should I take antibiotics?", "top_k": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["chunks"]) == 2
    assert body["chunks"][0]["source"] == "abx.pdf"
    assert 0 < body["chunks"][0]["similarity"] <= 1
    # lower distance -> higher similarity
    assert body["chunks"][0]["similarity"] > body["chunks"][1]["similarity"]


def test_retrieve_rejects_empty_question(client):
    r = client.post("/retrieve", json={"question": "", "top_k": 2})
    assert r.status_code == 422


def test_retrieve_rejects_top_k_out_of_range(client):
    r = client.post("/retrieve", json={"question": "hello", "top_k": 100})
    assert r.status_code == 422


def test_retrieve_empty_knowledge_base_returns_no_chunks(client, monkeypatch):
    import main as retrieval_main

    monkeypatch.setattr(retrieval_main, "count", lambda: 0)
    r = client.post("/retrieve", json={"question": "hello", "top_k": 3})
    assert r.status_code == 200
    assert r.json()["chunks"] == []
    assert r.json()["knowledge_base_size"] == 0
