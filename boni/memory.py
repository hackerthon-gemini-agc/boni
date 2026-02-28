"""Client-side long-term memory module — communicates with GCP backend."""

from datetime import datetime, timezone

import requests


class BoniMemory:
    """Long-term memory via GCP backend API."""

    TIMEOUT = 5  # seconds

    def __init__(self, backend_url: str, user_id: str = "anonymous"):
        self.backend_url = backend_url.rstrip("/")
        self.user_id = user_id

    def store(self, metrics: dict, reaction: dict) -> bool:
        """Store current metrics + reaction to backend.

        Returns True on success, False on any failure.
        Never raises — failures are silently logged.
        """
        try:
            payload = {
                "metrics": {
                    "cpu_percent": metrics.get("cpu_percent", 0),
                    "ram_percent": metrics.get("ram_percent", 0),
                    "battery_percent": metrics.get("battery_percent"),
                    "is_charging": metrics.get("is_charging", False),
                    "active_app": metrics.get("active_app", ""),
                    "running_apps": metrics.get("running_apps", 0),
                    "hour": metrics.get("hour", 0),
                    "minute": metrics.get("minute", 0),
                },
                "reaction": {
                    "message": reaction.get("message", ""),
                    "mood": reaction.get("mood", "chill"),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": self.user_id,
            }
            resp = requests.post(
                f"{self.backend_url}/api/v1/memories",
                json=payload,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            print(f"[boni memory] stored: {resp.json().get('id', '?')}")
            return True
        except Exception as e:
            print(f"[boni memory] store failed: {e}")
            return False

    def recall(self, metrics: dict, current_mood: str, top_k: int = 3) -> list:
        """Search for past memories similar to the current state.

        Returns a list of memory dicts, or empty list on failure.
        Never raises — failures return empty list.
        """
        try:
            # Build a query string similar to what the backend embeds
            battery_str = (
                f"{metrics.get('battery_percent', '?')}%"
                if metrics.get("battery_percent") is not None
                else "N/A"
            )
            query = (
                f"CPU load: {metrics.get('cpu_percent', 0)}%, "
                f"RAM: {metrics.get('ram_percent', 0)}%, "
                f"Battery: {battery_str}, "
                f"Active app: {metrics.get('active_app', 'Unknown')}, "
                f"Time: {metrics.get('hour', 0)}:{metrics.get('minute', 0):02d}, "
                f"Mood: {current_mood}"
            )
            resp = requests.post(
                f"{self.backend_url}/api/v1/memories/search",
                json={"query": query, "top_k": top_k, "user_id": self.user_id},
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("memories", [])
        except Exception as e:
            print(f"[boni memory] recall failed: {e}")
            return []
