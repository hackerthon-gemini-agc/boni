"""Cloud Storage integration for raw memory JSON storage."""

import json
from datetime import datetime

from google.cloud import storage


class MemoryStorage:
    """Read/write memory records to Cloud Storage."""

    def __init__(self, bucket_name: str = "boni-memories"):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def save(self, memory_id: str, data: dict) -> str:
        """Save raw memory JSON to GCS.

        Path format: raw/{date}/{memory_id}.json
        """
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        blob_path = f"raw/{date_str}/{memory_id}.json"
        blob = self.bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, default=str),
            content_type="application/json",
        )
        return blob_path

    def load(self, memory_id: str, date_str: str) -> dict | None:
        """Load a memory record by ID and date."""
        blob_path = f"raw/{date_str}/{memory_id}.json"
        blob = self.bucket.blob(blob_path)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())

    def load_by_path(self, blob_path: str) -> dict | None:
        """Load a memory record by its full blob path."""
        blob = self.bucket.blob(blob_path)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
