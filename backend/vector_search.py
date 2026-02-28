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
        """Upsert a single vector into the deployed index."""
        self.endpoint.match_engine_index_endpoint.upsert_datapoints(
            deployed_index_id=self.deployed_index_id,
            datapoints=[
                {
                    "datapoint_id": datapoint_id,
                    "feature_vector": embedding,
                }
            ],
        )

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
