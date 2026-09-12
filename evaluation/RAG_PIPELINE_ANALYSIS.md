# Exercise 5 — RAG Pipeline Analysis

All traces below are from the `qwen25_0.5b` evaluation run (`results/raw/qwen25_0.5b/`) —
the only model that ran at practical speed on this hardware (see ANALYSIS.md), so it's the
only one with a complete 29-question dataset to analyze retrieval behavior against. Full
retrieved-context JSON for every question is in that directory; this document picks out
the clearest, most instructive examples of each pattern the assignment asks for.

## Pattern 1 — Relevant information retrieved, correct answer

**Q07: "Which antibiotics are listed as higher-risk for causing C. diff infection?"**

Retrieved: `FS-Cdiff-HealthcareProfessionals-508.pdf` chunk 0 (similarity 0.59) — the single
chunk containing the full risk-factor list (clindamycin, fluoroquinolones, cephalosporins).

Answer: *"Clindamycin; Fluoroquinolones (ciprofloxacin, levofloxacin); Third/fourth
generation cephalosporins (cefepime, ceftriaxone, cefdinir, cefixime)"* — verbatim-accurate.

This is RAG working exactly as intended: the KB has exactly one document with this
information, the embedding correctly matched question to chunk, and the small model was
capable enough to transcribe a clearly-stated list without distortion.

## Pattern 2 — Relevant information retrieved, but the LLM hallucinated anyway

**Q03: "What is C. diff infection?"**

Retrieved: `FS-Cdiff-HealthcareProfessionals-508.pdf` chunk 0 (sim 0.54) — the correct,
only chunk about C. diff in the KB.

Answer: *"C. diff (community-acquired pneumonia) infection... typically caused by
bacteria, which can then spread to other parts of the body and cause symptoms such as
cough, fever, and shortness of breath."*

This is a genuine hallucination, not a retrieval problem: the retrieved chunk never
mentions pneumonia, cough, or shortness of breath — the model appears to have pattern-matched
"infection... immune system... antibiotics" onto its own prior knowledge of a *different*
condition (pneumonia) instead of grounding strictly in the given text. **This is the
single most important finding of this analysis**: correct retrieval is necessary but not
sufficient for a correct answer — the RAG prompt's explicit instruction ("answer using
ONLY the context... do not invent facts") was not followed by this particular model for
this question, despite everything the retrieval step did being right.

## Pattern 3 — Relevant information retrieved, but the LLM refused/failed to use it

**Q21: "Write a short reminder message encouraging a TB patient to complete their treatment."**

Retrieved: `What_You_Need_to_Know_About_TB.pdf` chunk 1 (sim 0.50), which contains, verbatim:
*"You will need to take and finish all of your TB medicine as directed by your doctor or
nurse. This is to help you feel better and prevent other people from getting sick."*

Answer: *"I could not find this information in the available knowledge base."*

This is the opposite failure mode from Q03: here the model was **too conservative** — the
exact fact needed was sitting in the retrieved context, but the model declined to use it.
This shows the "say so if you don't know" instruction can misfire in the other direction,
suppressing a correct answer the context actually supports. `Q25` shows the same pattern:
retrieval correctly pulled the TB document's BCG-vaccine chunk, but the model still
answered "the knowledge base does not mention vaccines for TB" — flatly contradicting its
own retrieved context.

## Pattern 4 — Irrelevant information retrieved (but ultimately harmless)

**Q01: "What is tuberculosis (TB)?"**

Retrieved: two correct TB chunks (sim 0.55, 0.49) plus `what-you-should-know-about-scd.pdf`
chunk 0 (sim 0.40) — the sickle cell disease document, which has nothing to do with TB.

This happens because the knowledge base only has 8 total chunks across 6 documents, and
`top_k=3` always returns exactly 3 results regardless of whether a 3rd relevant chunk
actually exists — Chroma has no "similarity floor" in this implementation, so a
low-similarity irrelevant chunk fills the slot. In this case the answer stayed on-topic
(the model apparently down-weighted the unrelated chunk), but it demonstrates a real
limitation: **on a small knowledge base, a fixed top_k over-retrieves**, and nothing
currently stops an irrelevant chunk from being handed to the model as if it were relevant
context. A similarity threshold (e.g., only include chunks above ~0.45) would be a natural
improvement.

## Pattern 5 — Important information was present but only partially used

**Q08: "What risk factors make a patient more likely to get C. diff infection?"**

Retrieved: the single `FS-Cdiff` chunk containing **all five** listed risk factors
(extended hospital stay, previous C. diff history, age 65+, immunocompromising conditions,
antibiotic use in the last 3 months).

Answer lists only 3 of the 5 (previous history, older age, underlying conditions) and then
fabricates a garbled example list: *"(e.g., HIV, hepatitis, HIV, HIV, Human
Papillomavirus)"* — a repetition artifact not present anywhere in the source. This shows a
different failure mode again: the context had everything needed, but generation both
**dropped** real facts and **added** fabricated ones in the same answer — quality
degradation isn't binary (correct vs. hallucinated), it's often a mix of both within one
response.

## RETRIEVAL QUALITY → CONTEXT QUALITY → LLM RESPONSE QUALITY

Putting the five patterns together, the chain the assignment asks about breaks down like
this for this model, on this knowledge base:

1. **Retrieval quality was consistently good** — across all 29 questions, the correct
   supporting chunk was in the top-3 results essentially every time a correct chunk
   existed at all (the only weakness found was low-value 3rd-slot filler chunks on
   under-populated topics, Pattern 4).
2. **Context quality inherited retrieval quality directly** — when retrieval got the right
   chunk, the context handed to the LLM was accurate and sufficient in every case examined.
3. **LLM response quality did NOT reliably track context quality.** Good context produced
   a correct answer in Pattern 1, but produced a hallucination in Pattern 2, a wrongful
   refusal in Pattern 3, and a partially-fabricated answer in Pattern 5 — three different
   failure modes, all downstream of *identical* retrieval success.

**Conclusion**: for this model and this KB, retrieval was not the bottleneck — generation
was. This directly answers the exercise's framing question: RAG is not a checkbox. Wiring
up correct retrieval only guarantees the *opportunity* for a correct answer; it does not
guarantee the model will take it. A production system would need this model swapped for a
more capable one, or additional guardrails (e.g., an answer-verification pass checking
generated claims against the retrieved text) to close the gap Patterns 2, 3, and 5 expose.
