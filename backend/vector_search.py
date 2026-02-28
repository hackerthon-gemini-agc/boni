"""Vertex AI Vector Search integration for memory indexing and retrieval."""

import os

from google.cloud import aiplatform
from google.cloud.aiplatform.matching_engine import MatchingEngineIndexEndpoint


class VectorSearchClient:
    """Client for Vertex AI Vector Search (Matching Engine)."""

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        index_endpoint_id: str | None = None,
        deployed_index_id: str | None = None,
    ):
        self.project = project or os.environ.get("GCP_PROJECT", "gemini-hackathon-488801")
        self.location = location or os.environ.get("GCP_LOCATION", "asia-northeast3")
        self.index_endpoint_id = index_endpoint_id or os.environ.get("VECTOR_SEARCH_ENDPOINT_ID", "")
        self.deployed_index_id = deployed_index_id or os.environ.get("VECTOR_SEARCH_DEPLOYED_INDEX_ID", "")

        aiplatform.init(project=self.project, location=self.location)

        self._endpoint: MatchingEngineIndexEndpoint | None = None

    @property
    def endpoint(self) -> MatchingEngineIndexEndpoint:
        if self._endpoint is None:
            self._endpoint = MatchingEngineIndexEndpoint(self.index_endpoint_id)
        return self._endpoint

    def upsert(self, datapoint_id: str, embedding: list[float]) -> None:
        """Upsert a single vector into the deployed index via REST API."""
        import google.auth
        import google.auth.transport.requests
        import requests

        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        # Use the index resource directly for upsert (not the endpoint)
        # Get the index ID from the deployed index
        index_id = self._get_index_id()
        url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project}/locations/{self.location}/"
            f"indexes/{index_id}:upsertDatapoints"
        )
        payload = {
            "datapoints": [
                {
                    "datapointId": datapoint_id,
                    "featureVector": embedding,
                }
            ]
        }
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        resp.raise_for_status()

    def _get_index_id(self) -> str:
        """Extract the index ID from the deployed index on the endpoint."""
        if not hasattr(self, "_index_id_cache"):
            # List deployed indexes to find the index resource
            for deployed in self.endpoint.deployed_indexes:
                if deployed.id == self.deployed_index_id:
                    # index is like projects/.../locations/.../indexes/XXXX
                    self._index_id_cache = deployed.index.split("/")[-1]
                    break
            else:
                # Fallback: use env var
                self._index_id_cache = os.environ.get("VECTOR_SEARCH_INDEX_ID", "")
        return self._index_id_cache

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """Search for nearest neighbors by embedding vector.

        Returns list of {"id": str, "distance": float}.
        """
        responses = self.endpoint.find_neighbors(
            deployed_index_id=self.deployed_index_id,
            queries=[query_embedding],
            num_neighbors=top_k,
        )

        results = []
        if responses:
            for neighbor in responses[0]:
                results.append({
                    "id": neighbor.id,
                    "distance": neighbor.distance,
                })
        return results
