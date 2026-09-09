import logging

import requests

from config import NUM_PREDICT, OLLAMA_MODEL, OLLAMA_URL, REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger("llm_service.ollama_client")


class OllamaError(Exception):
    """Raised when Ollama is unreachable, times out, or returns an error."""


def generate(prompt: str) -> str:
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": NUM_PREDICT},
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as exc:
        raise OllamaError(f"Ollama request timed out after {REQUEST_TIMEOUT_SECONDS}s") from exc
    except requests.exceptions.ConnectionError as exc:
        raise OllamaError(f"Could not reach Ollama at {OLLAMA_URL}") from exc

    if response.status_code != 200:
        raise OllamaError(f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")

    try:
        body = response.json()
    except ValueError as exc:
        raise OllamaError("Ollama returned a non-JSON response") from exc

    if "response" not in body:
        # Common case: model tag hasn't been pulled yet.
        raise OllamaError(f"Unexpected Ollama response (is model '{OLLAMA_MODEL}' pulled?): {body}")

    return body["response"]
