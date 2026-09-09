# ARCHITECTURE.md

## High-level architecture

```mermaid
flowchart LR
    U[User] --> F[Gradio Frontend :7860]
    F -->|POST /chat| A[Application / Orchestration Service :8000]
    A -->|POST /retrieve| R[Retrieval Service :8000]
    R --> V[(ChromaDB\nclinical_docs)]
    V --> R
    R --> A
    A -->|POST /generate| L[LLM Service :8000]
    L -->|POST /api/generate| O[Ollama :11434]
    O --> C[Code Llama\ncodellama:7b-instruct-q4_K_M]
    C --> O
    O --> L
    L --> A
    A --> F
    F --> U
```

## Component / service diagram

```mermaid
flowchart TB
    subgraph Frontend Service
        FE[Gradio app<br/>frontend/main.py]
    end

    subgraph Application/Orchestration Service
        AS[FastAPI<br/>app_service/main.py]
        ORCH[orchestrator.py<br/>builds RAG prompt,<br/>calls downstream services]
        AS --> ORCH
    end

    subgraph Retrieval Service
        RS[FastAPI<br/>retrieval_service/main.py]
        EMB[embeddings.py<br/>all-MiniLM-L6-v2]
        VS[vector_store.py<br/>ChromaDB client]
        ING[ingest.py<br/>one-off ingestion job]
        RS --> EMB
        RS --> VS
        ING --> EMB
        ING --> VS
    end

    subgraph LLM Service
        LS[FastAPI<br/>llm_service/main.py]
        OC[ollama_client.py]
        LS --> OC
    end

    subgraph Knowledge Base
        DOCS[(./docs PDFs)]
        CHROMA[(ChromaDB volume)]
    end

    FE -->|/chat| AS
    ORCH -->|/retrieve| RS
    ORCH -->|/generate| LS
    OC -->|/api/generate| OLLAMA[(Ollama + Code Llama)]
    VS --> CHROMA
    ING --> DOCS
```

## RAG flow (use_rag = true)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as app_service
    participant R as retrieval_service
    participant V as ChromaDB
    participant L as llm_service
    participant O as Ollama/Code Llama

    U->>F: question, RAG=ON, top_k=3
    F->>A: POST /chat {message, use_rag:true, top_k:3}
    A->>R: POST /retrieve {question, top_k:3}
    R->>R: embed_text(question) [all-MiniLM-L6-v2]
    R->>V: query(embedding, n_results=3)
    V-->>R: documents, metadatas, distances
    R-->>A: chunks [text, source, chunk_id, similarity]
    A->>A: build grounded prompt (system instructions + context + question)
    A->>L: POST /generate {prompt}
    L->>O: POST /api/generate {model: codellama, prompt}
    O-->>L: generated answer
    L-->>A: {answer, model}
    A-->>F: {answer, used_rag:true, sources, retrieved_context}
    F-->>U: answer + "RAG ON" banner + retrieved chunks + sources
```

## Non-RAG flow (use_rag = false)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as app_service
    participant L as llm_service
    participant O as Ollama/Code Llama

    U->>F: question, RAG=OFF
    F->>A: POST /chat {message, use_rag:false}
    A->>L: POST /generate {prompt: message}
    L->>O: POST /api/generate {model: codellama, prompt}
    O-->>L: generated answer
    L-->>A: {answer, model}
    A-->>F: {answer, used_rag:false, sources:[], retrieved_context:[]}
    F-->>U: answer + "RAG OFF" banner (no context shown)
```

## API flow (summary)

```mermaid
flowchart LR
    subgraph Public
        FE[frontend :7860]
    end
    subgraph Internal only - not exposed to internet
        AS[app_service :8000]
        RS[retrieval_service :8000]
        LS[llm_service :8000]
        OL[ollama :11434]
    end
    FE -->|/chat| AS
    AS -->|/retrieve| RS
    AS -->|/generate| LS
    LS -->|/api/generate| OL
```

## Docker architecture

```mermaid
flowchart TB
    subgraph "Docker host (Mac for dev, single EC2 instance for demo/viva)"
        direction TB
        subgraph compose_network["Default Compose network (service-name DNS)"]
            ollama_c[ollama container<br/>volume: ollama_data]
            pull_c[ollama_pull<br/>one-off: pulls Code Llama]
            ingest_c[kb_ingest<br/>one-off: builds vector index]
            llm_c[llm_service container]
            retr_c[retrieval_service container<br/>volumes: ./docs ro, chroma_data]
            app_c[app_service container]
            fe_c[frontend container]
        end
        pull_c --> ollama_c
        llm_c --> ollama_c
        ingest_c --> retr_c
        app_c --> llm_c
        app_c --> retr_c
        fe_c --> app_c
    end
    Browser((Mac browser)) -->|:7860| fe_c
```

Key rule enforced throughout: containers address each other by **Compose service name**
(`http://llm_service:8000`), never `localhost` — `localhost` inside a container means
"this container," which was the root cause of the original `app_service` bug (see
[PROJECT_AUDIT.md](PROJECT_AUDIT.md) §13/§16).

## AWS architecture

```mermaid
flowchart TB
    subgraph Mac
        Browser
    end
    subgraph "AWS EC2 (t3.xlarge, single instance)"
        direction TB
        SG[Security Group\ninbound: 22 SSH, 7860 Gradio\n(8000/11434 stay internal)]
        subgraph Docker on EC2
            fe[frontend :7860]
            app[app_service]
            retr[retrieval_service]
            llm[llm_service]
            ollama[ollama + Code Llama]
        end
        EBS[(30GB gp3 EBS\nmodel weights + chroma index)]
    end
    Browser -->|https/http :7860| SG --> fe
    fe --> app --> retr
    app --> llm --> ollama
    ollama --- EBS
    retr --- EBS
```

Rationale for one instance rather than ECS/ECR/App-Runner: it is the cheapest and easiest
architecture for a student to explain end-to-end in a viva, while still satisfying "the
LLM runs in the cloud, not on my Mac." See README.md §15 for sizing and cost details, and
PROJECT_AUDIT.md §19/§20 for the risk tradeoffs considered.

## Data flow (ingestion)

```mermaid
flowchart LR
    PDF[PDF/TXT files in ./docs] --> EXTRACT[extract_text\npypdf]
    EXTRACT --> CLEAN[clean_text\nwhitespace/newline normalization]
    CLEAN --> CHUNK[chunk_text\nCHUNK_SIZE=500 words\nCHUNK_OVERLAP=50 words]
    CHUNK --> EMBED[embed_texts\nall-MiniLM-L6-v2, 384-dim]
    EMBED --> STORE[(ChromaDB upsert\nid, embedding, text,\nmetadata: source/doc_id/chunk_id)]
```

## Request lifecycle (end to end, RAG on)

1. Gradio frontend collects `message`, `use_rag`, `top_k` and POSTs to `app_service /chat`.
2. `app_service` validates the request (Pydantic), logs it, and — because `use_rag=true`
   — calls `retrieval_service /retrieve`.
3. `retrieval_service` embeds the question, runs a ChromaDB similarity search, converts
   L2 distance to a 0-1 similarity score, and returns chunks with `source`/`chunk_id`.
4. `app_service` builds a system+context+question prompt instructing the model to answer
   only from context and say so explicitly if the answer isn't present.
5. `app_service` calls `llm_service /generate`, which forwards to Ollama's
   `/api/generate` with the `codellama:7b-instruct-q4_K_M` model tag.
6. The generated answer flows back through `llm_service` → `app_service` → the frontend,
   which renders the answer, the RAG-ON banner, the retrieved chunks (with similarity
   scores), and the source document list.
