import os

RETRIEVAL_SERVICE_URL = os.getenv("RETRIEVAL_SERVICE_URL", "http://retrieval_service:8000")
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm_service:8000")

DEFAULT_TOP_K = int(os.getenv("TOP_K", "3"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("APP_REQUEST_TIMEOUT", "10"))
LLM_REQUEST_TIMEOUT_SECONDS = int(os.getenv("APP_LLM_TIMEOUT", "120"))
