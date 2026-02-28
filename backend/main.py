"""FastAPI backend for boni long-term memory system."""

import os
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException
from google.cloud import aiplatform

from .models import (
    MemoryCreate,
    MemoryRecord,
    MemorySearchResult,
    SearchRequest,
    SearchResponse,
)
from .storage import MemoryStorage
from .embeddings import compose_embedding_text, generate_embedding
from .vector_search import VectorSearchClient

app = FastAPI(title="boni memory", version="0.1.0")

# Initialize services (lazy — created on first request)
_storage: MemoryStorage | None = None
_vector_search: VectorSearchClient | None = None


def get_storage() -> MemoryStorage:
    global _storage
    if _storage is None:
        bucket = os.environ.get("GCS_BUCKET", "boni-memories")
        _storage = MemoryStorage(bucket_name=bucket)
    return _storage


def get_vector_search() -> VectorSearchClient:
    global _vector_search
    if _vector_search is None:
        _vector_search = VectorSearchClient()
    return _vector_search


# ── Health check ─────────────────────────────────────────────────


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "boni-memory"}


# ── Store memory ─────────────────────────────────────────────────


@app.post("/api/v1/memories")
def store_memory(body: MemoryCreate):
    """Store a new memory: raw JSON → GCS, embedding → Vector Search."""
    memory_id = f"mem_{uuid.uuid4().hex[:12]}"

    # 1. Compose natural language summary for embedding
    metrics_dict = body.metrics.model_dump()
    reaction_dict = body.reaction.model_dump()
    embedding_text = compose_embedding_text(metrics_dict, reaction_dict)

    user_id = body.user_id

    # 2. Build full record
    record = MemoryRecord(
        id=memory_id,
        metrics=body.metrics,
        reaction=body.reaction,
        timestamp=body.timestamp,
        embedding_text=embedding_text,
        user_id=user_id,
    )

    # 3. Save raw JSON to Cloud Storage (scoped by user_id)
    storage = get_storage()
    storage.save(memory_id, record.model_dump(), user_id=user_id)

    # 4. Generate embedding and upsert to Vector Search (prefixed by user_id)
    embedding = generate_embedding(embedding_text)
    vs = get_vector_search()
    vs.upsert(memory_id, embedding, user_id=user_id)

    return {"id": memory_id, "status": "stored", "user_id": user_id}


# ── Search memories ──────────────────────────────────────────────


@app.post("/api/v1/memories/search", response_model=SearchResponse)
def search_memories(body: SearchRequest):
    """Search for similar past memories by query text."""
    # 1. Embed the query
    query_embedding = generate_embedding(body.query)

    # 2. Find nearest neighbors (filtered by user_id)
    vs = get_vector_search()
    neighbors = vs.search(query_embedding, top_k=body.top_k, user_id=body.user_id)

    if not neighbors:
        return SearchResponse(memories=[])

    # 3. Load full records from GCS
    storage = get_storage()
    results = []
    for neighbor in neighbors:
        mem_id = neighbor["id"]
        distance = neighbor["distance"]

        # Search across date directories for the memory (scoped by user_id)
        # Vector Search returns IDs, we need to find the corresponding GCS object
        raw_data = _find_memory_in_storage(storage, mem_id, user_id=body.user_id)
        if raw_data is None:
            continue

        results.append(
            MemorySearchResult(
                id=mem_id,
                timestamp=raw_data.get("timestamp", datetime.utcnow().isoformat()),
                reaction=raw_data.get("reaction", {"message": "", "mood": "chill"}),
                metrics=raw_data.get("metrics", {}),
                similarity=distance,
            )
        )

    return SearchResponse(memories=results)


def _find_memory_in_storage(storage: MemoryStorage, memory_id: str, user_id: str = "anonymous") -> dict | None:
    """Find a memory record in GCS by scanning date directories for a user."""
    from google.cloud import storage as gcs

    client = storage.client
    bucket = storage.bucket
    prefix = f"raw/{user_id}/"

    # List blobs matching the memory ID within user's directory
    blobs = list(bucket.list_blobs(prefix=prefix, match_glob=f"**/{memory_id}.json"))
    if blobs:
        import json
        return json.loads(blobs[0].download_as_text())

    return None
