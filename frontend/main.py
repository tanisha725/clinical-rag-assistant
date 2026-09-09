import os

import gradio as gr
import requests

APP_SERVICE_URL = os.getenv("APP_SERVICE_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("FRONTEND_TIMEOUT", "150"))

DESCRIPTION = """
Ask a clinical/public-health question. Use **Compare RAG ON vs OFF** to see, side by
side, a plain LLM answer against one grounded in the ingested knowledge base
(antibiotic safety, C. diff, TB, sickle cell disease, doxy-PEP documents) — or use
**Single Query** to toggle RAG on one answer at a time.
"""


def _call_chat(message: str, use_rag: bool, top_k: int):
    """Returns (answer, mode_banner, context_display) — or an error string in `answer`."""
    if not message or not message.strip():
        return "Please enter a question.", "", ""

    try:
        r = requests.post(
            f"{APP_SERVICE_URL}/chat",
            json={"message": message, "use_rag": use_rag, "top_k": top_k},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        return f"⚠️ Could not reach the application service: {exc}", "", ""

    if r.status_code != 200:
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        return f"⚠️ Request failed ({r.status_code}): {detail}", "", ""

    body = r.json()
    answer = body["answer"]

    if not body.get("used_rag"):
        mode_banner = "**Mode: RAG OFF** — question sent directly to the LLM, no retrieval performed."
        context_display = "_(RAG is off — no context was retrieved.)_"
        return answer, mode_banner, context_display

    sources = body.get("sources", [])
    chunks = body.get("retrieved_context", [])

    mode_banner = f"**Mode: RAG ON** — retrieved {len(chunks)} chunk(s) from {len(sources)} source document(s): {', '.join(sources) or 'none'}"

    if not chunks:
        context_display = "_No relevant chunks were found in the knowledge base for this question._"
    else:
        context_display = "\n\n".join(
            f"**[{i+1}] {c['source']}** (chunk {c['chunk_id']}, similarity {c['similarity']:.3f})\n\n> {c['text']}"
            for i, c in enumerate(chunks)
        )

    return answer, mode_banner, context_display


def ask(message: str, use_rag: bool, top_k: int):
    return _call_chat(message, use_rag, top_k)


def compare(message: str, top_k: int):
    off_answer, off_banner, _ = _call_chat(message, False, top_k)
    on_answer, on_banner, on_context = _call_chat(message, True, top_k)
    return off_answer, off_banner, on_answer, on_banner, on_context


with gr.Blocks(title="Clinical RAG Assistant") as demo:
    gr.Markdown("# Clinical RAG Assistant")
    gr.Markdown(DESCRIPTION)

    with gr.Tabs():
        with gr.Tab("Compare RAG ON vs OFF"):
            gr.Markdown("Runs the **same question** through both modes at once, so you can see exactly what retrieval changes.")
            cmp_question = gr.Textbox(label="Your question", placeholder="e.g. What should I know before taking antibiotics?", lines=2)
            cmp_top_k = gr.Slider(label="Top-K chunks (used only for the RAG ON side)", minimum=1, maximum=10, step=1, value=3)
            cmp_submit = gr.Button("Compare Both Modes", variant="primary")

            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 🔴 RAG OFF")
                    cmp_off_banner = gr.Markdown()
                    cmp_off_answer = gr.Textbox(label="Answer (no retrieval)", lines=8, interactive=False)
                with gr.Column():
                    gr.Markdown("### 🟢 RAG ON")
                    cmp_on_banner = gr.Markdown()
                    cmp_on_answer = gr.Textbox(label="Answer (grounded in knowledge base)", lines=8, interactive=False)
                    cmp_on_context = gr.Markdown(label="Retrieved context / sources")

            cmp_submit.click(
                fn=compare,
                inputs=[cmp_question, cmp_top_k],
                outputs=[cmp_off_answer, cmp_off_banner, cmp_on_answer, cmp_on_banner, cmp_on_context],
            )
            cmp_question.submit(
                fn=compare,
                inputs=[cmp_question, cmp_top_k],
                outputs=[cmp_off_answer, cmp_off_banner, cmp_on_answer, cmp_on_banner, cmp_on_context],
            )

        with gr.Tab("Single Query"):
            with gr.Row():
                with gr.Column(scale=2):
                    question = gr.Textbox(label="Your question", placeholder="e.g. What should I know before taking antibiotics?", lines=2)
                    with gr.Row():
                        use_rag = gr.Checkbox(label="Use RAG (retrieval-augmented generation)", value=True)
                        top_k = gr.Slider(label="Top-K chunks", minimum=1, maximum=10, step=1, value=3)
                    submit = gr.Button("Ask", variant="primary")

                with gr.Column(scale=3):
                    mode_indicator = gr.Markdown()
                    answer_box = gr.Textbox(label="Answer", lines=6, interactive=False)
                    context_box = gr.Markdown(label="Retrieved context / sources")

            submit.click(fn=ask, inputs=[question, use_rag, top_k], outputs=[answer_box, mode_indicator, context_box])
            question.submit(fn=ask, inputs=[question, use_rag, top_k], outputs=[answer_box, mode_indicator, context_box])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")))
