import os

DOCS_DIR = os.getenv("DOCS_DIR", "/app/docs")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "/app/chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "clinical_docs")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Word-based chunking. 500 words (~2-3 paragraphs) keeps enough surrounding
# context for the LLM to answer without truncation; 50-word overlap (10%)
# stops a sentence that straddles a chunk boundary from losing meaning on
# either side. Configurable via env because it directly affects retrieval
# quality and should be tunable without editing code.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

DEFAULT_TOP_K = int(os.getenv("TOP_K", "3"))
