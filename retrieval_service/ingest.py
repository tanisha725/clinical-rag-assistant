"""Knowledge-base ingestion pipeline: Documents -> Text Extraction -> Cleaning
-> Chunking -> Embedding -> Vector Database.

Run standalone: `python ingest.py`
Or via docker compose: `docker compose run --rm retrieval_service python ingest.py`
"""
import logging
import os
import re

from pypdf import PdfReader

from chunking import chunk_text
from config import CHUNK_OVERLAP, CHUNK_SIZE, DOCS_DIR
from embeddings import embed_texts
from vector_store import add_chunks, get_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest")


def extract_text(filepath: str) -> str:
    if filepath.lower().endswith(".pdf"):
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def run(docs_dir: str = DOCS_DIR) -> int:
    if not os.path.isdir(docs_dir):
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    filenames = sorted(
        f for f in os.listdir(docs_dir)
        if not f.startswith(".") and f.lower().endswith((".pdf", ".txt"))
    )
    if not filenames:
        logger.warning("No .pdf/.txt files found in %s — knowledge base will be empty.", docs_dir)
        return 0

    total_chunks = 0
    for doc_id, filename in enumerate(filenames):
        filepath = os.path.join(docs_dir, filename)
        logger.info("Extracting text from %s", filename)
        text = clean_text(extract_text(filepath))
        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            logger.warning("No text extracted from %s, skipping", filename)
            continue

        embeddings = embed_texts(chunks)
        ids = [f"doc{doc_id}-chunk{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": filename, "doc_id": doc_id, "chunk_id": i}
            for i in range(len(chunks))
        ]
        add_chunks(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
        logger.info("Indexed %d chunks from %s", len(chunks), filename)
        total_chunks += len(chunks)

    logger.info("Ingestion complete: %d chunks from %d documents.", total_chunks, len(filenames))
    return total_chunks


if __name__ == "__main__":
    run()
    logger.info("Collection now holds %d vectors.", get_collection().count())
