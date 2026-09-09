import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ROOT, "llm_service")


@pytest.fixture
def modules():
    for name in ("config", "main", "ollama_client"):
        sys.modules.pop(name, None)
    original_path = list(sys.path)
    sys.path.insert(0, SERVICE_DIR)

    import main as llm_main
    import ollama_client

    yield llm_main, ollama_client

    sys.path = original_path
    for name in ("config", "main", "ollama_client"):
        sys.modules.pop(name, None)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception(f"HTTP {self.status_code}")


def test_generate_success(modules, monkeypatch):
    llm_main, ollama_client = modules
    monkeypatch.setattr(
        ollama_client.requests, "post",
        lambda *a, **k: FakeResponse(200, {"response": "Take antibiotics as prescribed."}),
    )
    client = TestClient(llm_main.app)
    r = client.post("/generate", json={"prompt": "What should I know about antibiotics?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Take antibiotics as prescribed."
    assert r.json()["model"] == llm_main.OLLAMA_MODEL


def test_generate_rejects_empty_prompt(modules):
    llm_main, _ = modules
    client = TestClient(llm_main.app)
    r = client.post("/generate", json={"prompt": ""})
    assert r.status_code == 422


def test_generate_returns_502_when_ollama_unreachable(modules, monkeypatch):
    import requests as requests_lib

    llm_main, ollama_client = modules

    def raise_conn_error(*a, **k):
        raise requests_lib.exceptions.ConnectionError("refused")

    monkeypatch.setattr(ollama_client.requests, "post", raise_conn_error)
    client = TestClient(llm_main.app)
    r = client.post("/generate", json={"prompt": "hello"})
    assert r.status_code == 502


def test_generate_returns_502_on_timeout(modules, monkeypatch):
    import requests as requests_lib

    llm_main, ollama_client = modules

    def raise_timeout(*a, **k):
        raise requests_lib.exceptions.Timeout("timed out")

    monkeypatch.setattr(ollama_client.requests, "post", raise_timeout)
    client = TestClient(llm_main.app)
    r = client.post("/generate", json={"prompt": "hello"})
    assert r.status_code == 502


def test_health_reports_model_pulled_status(modules, monkeypatch):
    llm_main, _ = modules
    monkeypatch.setattr(
        llm_main.requests, "get",
        lambda *a, **k: FakeResponse(200, {"models": [{"name": llm_main.OLLAMA_MODEL}]}),
    )
    client = TestClient(llm_main.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["model_pulled"] is True


def test_health_degraded_when_ollama_unreachable(modules, monkeypatch):
    import requests as requests_lib

    llm_main, _ = modules

    def raise_conn_error(*a, **k):
        raise requests_lib.exceptions.ConnectionError("refused")

    monkeypatch.setattr(llm_main.requests, "get", raise_conn_error)
    client = TestClient(llm_main.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
