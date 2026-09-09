import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ROOT, "app_service")

MODULE_NAMES = ("config", "main", "models", "services", "services.orchestrator")


@pytest.fixture
def modules():
    for name in MODULE_NAMES:
        sys.modules.pop(name, None)
    original_path = list(sys.path)
    sys.path.insert(0, SERVICE_DIR)

    import main as app_main
    from services import orchestrator

    yield app_main, orchestrator

    sys.path = original_path
    for name in MODULE_NAMES:
        sys.modules.pop(name, None)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def test_chat_without_rag_skips_retrieval(modules, monkeypatch):
    app_main, orchestrator = modules
    calls = []

    def fake_post(url, json, timeout):
        calls.append(url)
        return FakeResponse(200, {"answer": "Direct answer, no context.", "model": "codellama:7b-instruct-q4_K_M"})

    monkeypatch.setattr(orchestrator.requests, "post", fake_post)
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "What is TB?", "use_rag": False})

    assert r.status_code == 200
    body = r.json()
    assert body["used_rag"] is False
    assert body["sources"] == []
    assert not any("retrieve" in c for c in calls)


def test_chat_with_rag_calls_retrieval_then_llm_and_returns_sources(modules, monkeypatch):
    app_main, orchestrator = modules
    calls = []

    def fake_post(url, json, timeout):
        calls.append(url)
        if "retrieve" in url:
            return FakeResponse(200, {"chunks": [
                {"text": "Finish your antibiotics course.", "source": "abx.pdf", "chunk_id": 0, "similarity": 0.9}
            ]})
        return FakeResponse(200, {"answer": "Finish your full course of antibiotics.", "model": "codellama:7b-instruct-q4_K_M"})

    monkeypatch.setattr(orchestrator.requests, "post", fake_post)
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "How do I take antibiotics?", "use_rag": True, "top_k": 2})

    assert r.status_code == 200
    body = r.json()
    assert body["used_rag"] is True
    assert body["sources"] == ["abx.pdf"]
    assert len(body["retrieved_context"]) == 1
    assert any("retrieve" in c for c in calls)
    assert any("generate" in c for c in calls)


def test_chat_rejects_empty_message(modules):
    app_main, _ = modules
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "", "use_rag": True})
    assert r.status_code == 422


def test_chat_returns_502_when_retrieval_service_down(modules, monkeypatch):
    app_main, orchestrator = modules

    def fake_post(url, json, timeout):
        import requests
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(orchestrator.requests, "post", fake_post)
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "hello", "use_rag": True})
    assert r.status_code == 502
    assert "retrieval_service" in r.json()["detail"]


def test_chat_returns_502_when_llm_service_down(modules, monkeypatch):
    app_main, orchestrator = modules

    def fake_post(url, json, timeout):
        if "retrieve" in url:
            return FakeResponse(200, {"chunks": []})
        import requests
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(orchestrator.requests, "post", fake_post)
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "hello", "use_rag": True})
    assert r.status_code == 502
    assert "llm_service" in r.json()["detail"]


def test_chat_with_rag_and_no_matching_chunks_still_answers(modules, monkeypatch):
    app_main, orchestrator = modules

    def fake_post(url, json, timeout):
        if "retrieve" in url:
            return FakeResponse(200, {"chunks": []})
        return FakeResponse(200, {"answer": "I could not find this information in the available knowledge base.", "model": "x"})

    monkeypatch.setattr(orchestrator.requests, "post", fake_post)
    client = TestClient(app_main.app)
    r = client.post("/chat", json={"message": "hello", "use_rag": True})
    assert r.status_code == 200
    assert r.json()["sources"] == []
