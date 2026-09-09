FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ingestion is NOT run at build time (a fresh doc set or chunking config
# would then require a full image rebuild). Run it once at container
# startup / via `docker compose run --rm retrieval_service python ingest.py`.
# The embedding model + chroma index live under /app/chroma_db, which is
# mounted as a volume in docker-compose.yml so they persist across restarts.

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
