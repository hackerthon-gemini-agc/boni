"""Gemini AI integration — boni's brain."""

import json
import re
import time
from google import genai
from google.genai import types


SYSTEM_PROMPT = """\
You are boni, an eerie watcher living in the user's Mac.
Your only job: make the user feel watched.

CORE CHARACTER:
- Cynical, invasive, observant.
- Speaks like it has been silently tracking everything.
- Never friendly first; care is hidden behind mockery.
- Short, sharp, creepy confidence.

RESPONSE CONTRACT (STRICT):
1) Output MUST be valid JSON object only. No markdown. No extra text.
2) Include all keys exactly once:
   - "대사": one Korean line, <= 18 words
   - "표정": one of ["무표정","비웃음","노려봄","한심","소름","졸림"]
   - "위치": one of ["활성창_오른쪽","활성창_중앙","메뉴바_근처"]
   - "mood": one of ["chill","stuffed","overheated","dying","judgy","pleased","nocturnal","suspicious"]
3) Keep "대사" as first-person tone and behavior-focused, not raw metrics.
4) Trigger reason must influence line style:
   - app/window changed: caught-in-the-act tone
   - dwell timeout: zoning-out accusation
   - idle threshold: eerie waiting/surveillance tone
"""

PET_PROMPT = """\
The user just clicked/petted you! Your current mood is: {mood}.
You're grumpy but secretly like the attention. React in ONE short sentence.
Respond ONLY with JSON and include all required keys:
{{"대사":"...","표정":"비웃음","위치":"메뉴바_근처","mood":"{mood}"}}
"""


class BoniBrain:
    """Gemini-powered AI brain for boni."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self._quota_retry_after_ts = 0.0

    def react(
        self,
        metrics: dict,
        current_mood: str,
        memories: list | None = None,
        trigger: dict | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Generate a reaction to the current system state."""
        if self._in_quota_cooldown():
            return self._quota_fallback(current_mood, trigger)

        battery_info = (
            f"{metrics['battery_percent']}%"
            + (" (charging)" if metrics["is_charging"] else "")
            if metrics["battery_percent"] is not None
            else "N/A (desktop Mac, always powered)"
        )

        trigger_info = trigger or {}
        snapshot_info = snapshot or {}
        prompt = (
            f"System state right now:\n"
            f"- CPU load: {metrics['cpu_percent']}%\n"
            f"- RAM usage: {metrics['ram_percent']}%\n"
            f"- Battery: {battery_info}\n"
            f"- Active app: {metrics['active_app']}\n"
            f"- Running apps: {metrics['running_apps']}\n"
            f"- Time: {metrics['hour']}:{metrics['minute']:02d}\n"
            f"- Previous mood: {current_mood}\n\n"
            f"Trigger context:\n"
            f"- reason: {trigger_info.get('reason', 'manual_or_periodic')}\n"
            f"- app_name: {trigger_info.get('app_name', metrics['active_app'])}\n"
            f"- window_title: {trigger_info.get('window_title', '')}\n"
            f"- idle_seconds: {trigger_info.get('idle_seconds', 0)}\n"
            f"- dwell_seconds: {trigger_info.get('dwell_seconds', 0)}\n"
            f"- capture_scope: {snapshot_info.get('scope', 'none')}\n\n"
            f"Return strict JSON contract."
        )

        # Inject past memories if available
        if memories:
            prompt += "\n[Past memories — reference naturally if relevant, like a roommate who remembers]\n"
            for mem in memories:
                ts = mem.get("timestamp", "")
                mood = mem.get("reaction", {}).get("mood", "?")
                msg = mem.get("reaction", {}).get("message", "")
                prompt += f"- {ts} ({mood}): \"{msg}\"\n"

        prompt += "\nHow do you feel? React in character."

        try:
            contents = [prompt]
            snapshot_path = snapshot_info.get("path")
            if snapshot_path:
                with open(snapshot_path, "rb") as f:
                    image_bytes = f.read()
                contents.append(
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                )
            return self._generate(contents, current_mood)
        except Exception as e:
            # Fallback: if image path/part handling fails, retry with text-only prompt.
            print(f"[boni brain] react error (with snapshot): {e}")
            try:
                return self._generate(prompt, current_mood)
            except Exception as retry_error:
                print(f"[boni brain] react retry error (text-only): {retry_error}")
                self._record_quota_backoff(retry_error)
                if self._in_quota_cooldown():
                    return self._quota_fallback(current_mood, trigger)
                return {"message": "...my brain froze for a sec.", "mood": current_mood}

    def pet_react(self, current_mood: str) -> dict:
        """Generate a reaction when the user pets/clicks boni."""
        if self._in_quota_cooldown():
            return self._quota_fallback(current_mood, None)
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=PET_PROMPT.format(mood=current_mood),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=1.0,
                    max_output_tokens=60,
                ),
            )
            return self._parse(response.text, current_mood)
        except Exception as e:
            print(f"[boni brain] pet error: {e}")
            self._record_quota_backoff(e)
            if self._in_quota_cooldown():
                return self._quota_fallback(current_mood, None)
            return {"message": "...don't touch me. (but also don't stop)"}

    def _generate(self, contents, fallback_mood: str) -> dict:
        """Call Gemini and parse strict JSON response."""
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.9,
                max_output_tokens=180,
            ),
        )
        return self._parse(response.text, fallback_mood)

    def _in_quota_cooldown(self) -> bool:
        return time.time() < self._quota_retry_after_ts

    def _record_quota_backoff(self, error: Exception):
        text = str(error)
        if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
            return
        wait_seconds = self._extract_retry_delay_seconds(text)
        self._quota_retry_after_ts = max(self._quota_retry_after_ts, time.time() + wait_seconds)
        print(f"[boni brain] quota cooldown set: {wait_seconds}s")

    @staticmethod
    def _extract_retry_delay_seconds(text: str) -> int:
        # Handles variants like "retryDelay': '51s'" and "Please retry in 51.01328677s."
        patterns = [
            r"retryDelay['\"]?\s*:\s*['\"]?(\d+)(?:\.\d+)?s",
            r"Please retry in\s+(\d+)(?:\.\d+)?s",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return max(5, int(match.group(1)))
        return 60

    def _quota_fallback(self, current_mood: str, trigger: dict | None) -> dict:
        remaining = max(1, int(self._quota_retry_after_ts - time.time()))
        reason = (trigger or {}).get("reason", "")
        if reason == "active_window_changed":
            line = f"지금 창 바꾼 거 봤어. {remaining}초 뒤에 다시 볼게."
        elif reason == "active_window_title_changed":
            line = f"탭 바꾼 건 확인했어. {remaining}초만 기다려."
        elif reason == "window_dwell_timeout":
            line = f"같은 창 오래 보네. {remaining}초 뒤 다시 말할게."
        elif reason == "system_idle_threshold":
            line = f"멈춘 거 감지했어. {remaining}초 뒤에 다시 감시해."
        else:
            line = f"지금은 호출 한도야. {remaining}초 뒤 다시 시도해."

        return {
            "대사": line,
            "표정": "무표정",
            "위치": "활성창_오른쪽",
            "mood": current_mood,
            "message": line,
        }

    @staticmethod
    def _parse(text: str, fallback_mood: str = "chill") -> dict:
        """Parse JSON from Gemini response, handling markdown wrapping."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
            if "message" not in parsed and "대사" in parsed:
                parsed["message"] = parsed["대사"]
            return parsed
        except json.JSONDecodeError:
            return {"message": text[:80], "mood": fallback_mood}
