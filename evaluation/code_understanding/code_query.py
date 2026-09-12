"""Exercise 6 — query the code_kb collection built by code_kb_ingest.py.

For each question: embed it, retrieve top-k code file chunks by similarity,
build a code-QA prompt, call Ollama directly (bypassing the app's llm_service
so this stays a self-contained, separate evaluation), and record
QUESTION -> RETRIEVED FILES -> ANSWER for manual grading against the
ground_truth in code_questions.json.

Run inside the retrieval_service container, after code_kb_ingest.py:
  docker exec <container> python /tmp/code_query.py
"""
import json
import os

import chromadb
import requests
from sentence_transformers import SentenceTransformer

CODE_DB_PATH = os.getenv("CODE_DB_PATH", "/tmp/code_kb_db")
COLLECTION_NAME = "code_kb"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama_smoketest:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b-instruct")
QUESTIONS_PATH = os.getenv("QUESTIONS_PATH", "/tmp/code_questions.json")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "/tmp/code_understanding_results.json")
TOP_K = 3

CODE_QA_PROMPT = """You are a code assistant answering questions about a software \
repository using ONLY the code excerpts below. Cite which file(s) support your \
answer. If the excerpts don't contain enough information, say so explicitly.

Code excerpts:
{context}

Question: {question}

Answer:"""


def main():
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CODE_DB_PATH)
    collection = client.get_collection(COLLECTION_NAME)

    with open(QUESTIONS_PATH) as f:
        questions = json.load(f)

    results = []
    for q in questions:
        embedding = model.encode(q["question"]).tolist()
        hits = collection.query(query_embeddings=[embedding], n_results=TOP_K, include=["documents", "metadatas", "distances"])
        retrieved_files = [
            {"file_path": meta["file_path"], "similarity": 1.0 / (1.0 + dist), "snippet": doc[:400]}
            for doc, meta, dist in zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0])
        ]
        context = "\n\n".join(f"[{r['file_path']}]\n{doc}" for r, doc in zip(retrieved_files, hits["documents"][0]))
        prompt = CODE_QA_PROMPT.format(context=context, question=q["question"])

        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"num_predict": 300}},
            timeout=300,
        )
        answer = r.json().get("response", f"ERROR: {r.text[:200]}")

        results.append({
            "id": q["id"],
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "retrieved_files": [{"file_path": r["file_path"], "similarity": r["similarity"]} for r in retrieved_files],
            "answer": answer,
        })
        print(f"{q['id']}: retrieved {[r['file_path'] for r in retrieved_files]}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
