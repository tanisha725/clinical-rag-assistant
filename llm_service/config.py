import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# Code Llama is required by the assignment (llama3.2:1b does NOT satisfy it).
# codellama:7b-instruct-q4_K_M is the quantized instruct variant: ~4GB on
# disk, runs on CPU with ~8GB RAM, and follows the RAG prompt's instructions
# far better than the base completion model. See README.md "AWS setup" for
# sizing notes and ARCHITECTURE.md for the resource-requirement discussion.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "codellama:7b-instruct-q4_K_M")

NUM_PREDICT = int(os.getenv("NUM_PREDICT", "300"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
