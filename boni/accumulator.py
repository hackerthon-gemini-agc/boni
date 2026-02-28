"""Event accumulator — batches sensor events and triggers AI only when significant."""

import time
from collections import deque


# Significance scores per event reason
SIGNIFICANCE = {
    "active_window_changed": 5.0,
    "active_window_title_changed": 0.5,
    "window_dwell_timeout": 3.0,
    "system_idle_threshold": 2.0,
    "frustration_pattern": 4.0,
    "sigh_detected": 3.0,
    "rapid_app_switching": 3.0,
    "high_typing_burst": 1.0,
}

TRIGGER_THRESHOLD = 5.0
MIN_INTERVAL_SECONDS = 0
MAX_INTERVAL_SECONDS = 120


class EventAccumulator:
    """Accumulates sensor events and decides when to trigger AI."""

    def __init__(self):
        self._events: list[dict] = []
        self._score: float = 0.0
        self._started_at: float = time.time()
        self._last_trigger_at: float = time.time()
        # Track recent app switches for rapid-switching detection
        self._recent_app_switches: deque[float] = deque(maxlen=10)

    def add_event(self, event: dict) -> bool:
        """Add an event and return True if AI should be triggered now."""
        reason = event.get("reason", "")
        score = SIGNIFICANCE.get(reason, 0.5)
        self._events.append(event)
        self._score += score

        # Track app switches for rapid-switching pattern
        if reason == "active_window_changed":
            self._recent_app_switches.append(time.time())
            self._detect_rapid_switching()

        now = time.time()
        elapsed = now - self._last_trigger_at

        # Force trigger after MAX_INTERVAL
        if elapsed >= MAX_INTERVAL_SECONDS and self._events:
            return True

        # Normal trigger: score threshold AND minimum interval
        if self._score >= TRIGGER_THRESHOLD and elapsed >= MIN_INTERVAL_SECONDS:
            return True

        return False

    def consume(self) -> dict:
        """Consume accumulated events, return summary dict, and reset."""
        now = time.time()
        duration = now - self._started_at

        # Find dominant pattern (highest-score reason)
        reason_scores: dict[str, float] = {}
        for ev in self._events:
            r = ev.get("reason", "unknown")
            reason_scores[r] = reason_scores.get(r, 0) + SIGNIFICANCE.get(r, 0.5)
        dominant = max(reason_scores, key=reason_scores.get) if reason_scores else "none"

        # Count app switches
        app_switches = sum(1 for e in self._events if e.get("reason") == "active_window_changed")

        # Collect recent events (last 5)
        recent = self._events[-5:]

        # Build behavior stats from events
        behavior_stats = {}
        for ev in self._events:
            for key in ("clicks_per_min", "typing_speed", "backspace_ratio", "sighs"):
                if key in ev:
                    behavior_stats[key] = ev[key]

        summary = {
            "duration_seconds": round(duration),
            "total_score": round(self._score, 1),
            "event_count": len(self._events),
            "dominant_pattern": dominant,
            "app_switches": app_switches,
            "recent_events": recent,
            "behavior_stats": behavior_stats,
        }

        # Reset
        self._events = []
        self._score = 0.0
        self._started_at = now
        self._last_trigger_at = now

        return summary

    def _detect_rapid_switching(self):
        """Detect rapid app switching (3+ switches within 30 seconds)."""
        now = time.time()
        # Remove old entries
        while self._recent_app_switches and now - self._recent_app_switches[0] > 30:
            self._recent_app_switches.popleft()

        if len(self._recent_app_switches) >= 3:
            # Inject a synthetic rapid_app_switching event
            self._events.append({
                "reason": "rapid_app_switching",
                "ts": now,
                "app_name": "",
                "window_title": "",
                "idle_seconds": 0,
                "dwell_seconds": 0,
            })
            self._score += SIGNIFICANCE["rapid_app_switching"]
            self._recent_app_switches.clear()
