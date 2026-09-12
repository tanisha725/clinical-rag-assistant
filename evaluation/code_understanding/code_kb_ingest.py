"""Exercise 6 — ingest OUR OWN project source code into a separate ChromaDB
collection, so we can test whether the RAG system can answer questions that
require understanding relationships across multiple files/services.

This is deliberately a SEPARATE knowledge base from the clinical PDFs
(collection "code_kb" at a separate path) -- it does not touch or affect the
production app's "clinical_docs" collection.

Run inside the retrieval_service container (has sentence-transformers +
chromadb already installed):
  docker cp <project_root> <container>:/tmp/project_src
  docker exec <container> python /tmp/code_kb_ingest.py
"""
import os

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/tmp/project_src")
CODE_DB_PATH = os.getenv("CODE_DB_PATH", "/tmp/code_kb_db")
COLLECTION_NAME = "code_kb"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

INCLUDE_DIRS = ["app_service", "retrieval_service", "llm_service", "frontend", "tests"]
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache"}


def collect_files() -> list[str]:
    files = []
    for d in INCLUDE_DIRS:
        base = os.path.join(PROJECT_ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, filenames in os.walk(base):
            dirs[:] = [x for x in dirs if x not in EXCLUDE_NAMES]
            for fn in filenames:
                if fn.endswith(".py"):
                    files.append(os.path.join(root, fn))
    return sorted(files)


def relpath(path: str) -> str:
    return os.path.relpath(path, PROJECT_ROOT)


def main():
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CODE_DB_PATH)
    # Fresh collection each run, so re-running after code changes doesn't
    # mix stale chunks with new ones.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    files = collect_files()
    ids, embeddings, documents, metadatas = [], [], [], []

    for i, path in enumerate(files):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            continue
        rel = relpath(path)
        # One chunk per file: every file in this project is short (<200
        # lines), so a per-file chunk keeps a function's full context
        # together, unlike splitting mid-function.
        text_for_embedding = f"# File: {rel}\n{content}"
        emb = model.encode(text_for_embedding).tolist()
        ids.append(f"file{i}")
        embeddings.append(emb)
        documents.append(content)
        metadatas.append({"file_path": rel, "service": rel.split(os.sep)[0]})

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    print(f"Indexed {len(ids)} files into '{COLLECTION_NAME}' at {CODE_DB_PATH}")
    for m in metadatas:
        print(" -", m["file_path"])


if __name__ == "__main__":
    main()
