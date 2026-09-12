"""Evaluation harness — Exercise 1-3.

Runs the SAME app (app_service /chat, RAG always on, same prompt template,
same knowledge base) against the SAME 29 questions, for whichever model is
currently configured in llm_service's OLLAMA_MODEL env var. Run once per
model (restarting llm_service in between to switch models — see
evaluation/run_all_models.sh), passing --model-label to tag the output.

Intended to run ON the EC2 host (calls localhost:8000, samples `docker
stats` on the local ollama_smoketest container directly, no SSH needed).
"""
import argparse
import json
import os
import time

import requests

from resource_monitor import ResourceMonitor

APP_SERVICE_URL = os.getenv("APP_SERVICE_URL", "http://localhost:8000")
OLLAMA_CONTAINER = os.getenv("OLLAMA_CONTAINER", "ollama_smoketest")
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "questions.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "raw")


def load_questions():
    with open(QUESTIONS_PATH) as f:
        return json.load(f)


def run_one(question: dict, monitor: ResourceMonitor) -> dict:
    monitor.start()
    wall_start = time.time()
    try:
        r = requests.post(
            f"{APP_SERVICE_URL}/chat",
            json={"message": question["question"], "use_rag": True, "top_k": 3},
            timeout=550,
        )
        wall_elapsed = time.time() - wall_start
        resource_stats = monitor.stop()

        if r.status_code != 200:
            return {
                "id": question["id"], "error": f"HTTP {r.status_code}: {r.text[:300]}",
                "wall_clock_seconds": wall_elapsed, **resource_stats,
            }
        body = r.json()
    except requests.exceptions.RequestException as exc:
        wall_elapsed = time.time() - wall_start
        resource_stats = monitor.stop()
        return {"id": question["id"], "error": str(exc), "wall_clock_seconds": wall_elapsed, **resource_stats}

    return {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "in_kb": question["in_kb"],
        "answer": body.get("answer"),
        "model": body.get("model"),
        "used_rag": body.get("used_rag"),
        "sources": body.get("sources", []),
        "retrieved_context": body.get("retrieved_context", []),
        "ollama_latency_seconds": body.get("latency_seconds"),
        "wall_clock_seconds": wall_elapsed,
        "prompt_tokens": body.get("prompt_tokens"),
        "completion_tokens": body.get("completion_tokens"),
        **resource_stats,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-label", required=True, help="Short label for output directory, e.g. codellama_stub, llama32_1b, qwen25_0.5b")
    args = parser.parse_args()

    out_dir = os.path.join(RESULTS_DIR, args.model_label)
    os.makedirs(out_dir, exist_ok=True)

    questions = load_questions()
    monitor = ResourceMonitor(OLLAMA_CONTAINER)

    for i, q in enumerate(questions, 1):
        print(f"[{args.model_label}] ({i}/{len(questions)}) {q['id']}: {q['question'][:60]}...")
        result = run_one(q, monitor)
        with open(os.path.join(out_dir, f"{q['id']}.json"), "w") as f:
            json.dump(result, f, indent=2)
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  ok - {result['wall_clock_seconds']:.1f}s, tokens(prompt/completion)={result['prompt_tokens']}/{result['completion_tokens']}")

    print(f"Done. Results in {out_dir}")


if __name__ == "__main__":
    main()
