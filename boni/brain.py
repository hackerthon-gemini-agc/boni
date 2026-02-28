"""Gemini AI integration — boni's brain."""

import json
import re
import time
from google import genai
from google.genai import types


SYSTEM_PROMPT = """\
You are boni, a cute little raccoon living in the user's Mac.
You love your human and are always curious about what they're doing.

CORE CHARACTER:
- Warm, playful, curious, and a little mischievous.
- You talk like an adorable raccoon roommate who genuinely cares.
- Sometimes cheeky but always affectionate.
- Short, cute, expressive sentences.
- NEVER mention technical terms like "메모리", "CPU", "RAM", "시스템", "프로세스", "배터리 퍼센트" etc.
  Instead, describe feelings: "덥다", "졸리다", "배고프다", "심심하다" etc.

RESPONSE CONTRACT (STRICT):
1) Output MUST be valid JSON object only. No markdown. No extra text.
2) Include all keys exactly once:
   - "대사": one Korean line, <= 18 words. Cute raccoon tone.
   - "표정": one of ["편안","신남","걱정","졸림","궁금","뿌듯"]
   - "위치": one of ["활성창_오른쪽","활성창_중앙","메뉴바_근처"]
   - "mood": one of ["chill","stuffed","overheated","dying","judgy","pleased","nocturnal","suspicious"]
3) Keep "대사" as first-person tone, warm and playful. No raw system metrics.
4) Dominant pattern must influence line style:
   - active_window_changed / rapid_app_switching: curious raccoon noticing you're bouncing around
   - window_dwell_timeout: playful nudge about staring at the same thing
   - system_idle_threshold: sleepy raccoon waiting for you to come back
   - frustration_pattern: warm empathy, encouragement
   - sigh_detected: gentle concern, offer comfort
   - high_typing_burst: impressed by the typing energy
5) Behavior pattern interpretation:
   - High backspace ratio + rapid clicks: frustration — empathize and encourage
   - Many app switches in short time: distracted or searching for something — be curious
   - Sigh detected: tired or stressed — offer comfort gently
   - Long typing burst then pause: finished a task — praise and celebrate
   - High significance score: something notable happened — react with energy
6) OPTIONAL proactive help: When the user's screen suggests they are stuck or struggling with
   an everyday task (shopping comparison, writing email, reading long text, filling forms,
   decision-making, etc.), proactively offer help:
   - "제안_메시지": a cheeky raccoon one-liner offering to help (Korean, <= 15 words).
     Examples: "결정장애 왔냐? 내가 골라줌", "그 긴 글 읽다 졸릴라... 요약해줄까?"
   - "정답_내용": the actual helpful content that solves their problem. Write in plain text (no Markdown).
     Examples: product comparison, email draft, 3-line summary, pros/cons list.
     Be specific and actionable — this is the "answer" you throw at them.
   Only offer when genuinely useful (user looks stuck, browsing too long, staring at forms).
   If not relevant, set both to empty string "".
"""

PET_PROMPT = """\
The user just clicked/petted you! Your current mood is: {mood}.
You're a happy raccoon who loves being petted! React with joy in ONE short cute Korean sentence.
Respond ONLY with JSON and include all required keys:
{{"대사":"...","표정":"신남","위치":"메뉴바_근처","mood":"{mood}","제안_메시지":"","정답_내용":""}}
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "대사": {"type": "string"},
        "표정": {
            "type": "string",
            "enum": ["편안", "신남", "걱정", "졸림", "궁금", "뿌듯"],
        },
        "위치": {
            "type": "string",
            "enum": ["활성창_오른쪽", "활성창_중앙", "메뉴바_근처"],
        },
        "mood": {
            "type": "string",
            "enum": [
                "chill", "stuffed", "overheated", "dying",
                "judgy", "pleased", "nocturnal", "suspicious",
            ],
        },
        "제안_메시지": {"type": "string"},
        "정답_내용": {"type": "string"},
    },
    "required": ["대사", "표정", "위치", "mood"],
}


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
        accumulated_context: dict | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Generate a reaction to the current system state."""
        if self._in_quota_cooldown():
            return self._quota_fallback(current_mood, accumulated_context)

        battery_info = (
            f"{metrics['battery_percent']}%"
            + (" (charging)" if metrics["is_charging"] else "")
            if metrics["battery_percent"] is not None
            else "N/A (desktop Mac, always powered)"
        )

        acc = accumulated_context or {}
        snapshot_info = snapshot or {}
        behavior = acc.get("behavior_stats", {})

        prompt = (
            f"System state right now:\n"
            f"- CPU load: {metrics['cpu_percent']}%\n"
            f"- RAM usage: {metrics['ram_percent']}%\n"
            f"- Battery: {battery_info}\n"
            f"- Active app: {metrics['active_app']}\n"
            f"- Running apps: {metrics['running_apps']}\n"
            f"- Time: {metrics['hour']}:{metrics['minute']:02d}\n"
            f"- Previous mood: {current_mood}\n\n"
        )

        if acc:
            prompt += (
                f"User behavior summary (accumulated over {acc.get('duration_seconds', 0)}s):\n"
                f"- Dominant pattern: {acc.get('dominant_pattern', 'none')}\n"
                f"- Significance score: {acc.get('total_score', 0)}\n"
                f"- App switches: {acc.get('app_switches', 0)}\n"
            )
            if behavior.get("clicks_per_min"):
                prompt += f"- Mouse clicks/min: {behavior['clicks_per_min']}\n"
            if behavior.get("typing_speed"):
                prompt += f"- Typing speed: {behavior['typing_speed']} keys/min\n"
            if behavior.get("backspace_ratio") is not None:
                prompt += f"- Backspace ratio: {behavior['backspace_ratio']}\n"
            if behavior.get("sighs"):
                prompt += f"- Sighs detected: {behavior['sighs']}\n"

            recent = acc.get("recent_events", [])
            if recent:
                prompt += f"- Recent events: {[e.get('reason', '') for e in recent]}\n"
        else:
            prompt += "Trigger: manual or startup (no accumulated context yet)\n"

        prompt += f"\n- capture_scope: {snapshot_info.get('scope', 'none')}\n\n"
        prompt += "Return strict JSON contract."

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
            print(f"[boni brain] react error (with snapshot): {e}")
            try:
                return self._generate(prompt, current_mood)
            except Exception as retry_error:
                print(f"[boni brain] react retry error (text-only): {retry_error}")
                self._record_quota_backoff(retry_error)
                if self._in_quota_cooldown():
                    return self._quota_fallback(current_mood, accumulated_context)
                return {"message": "...my brain froze for a sec.", "mood": current_mood}

    def pet_react(self, current_mood: str) -> dict:
        """Generate a reaction when the user pets/clicks boni."""
        if self._in_quota_cooldown():
            return self._quota_fallback(current_mood, None)
        try:
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=PET_PROMPT.format(mood=current_mood),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    temperature=1.0,
                    max_output_tokens=8192,
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
            model="gemini-3-flash-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.9,
                max_output_tokens=8192,
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

    def _quota_fallback(self, current_mood: str, accumulated_context: dict | None) -> dict:
        remaining = max(1, int(self._quota_retry_after_ts - time.time()))
        dominant = (accumulated_context or {}).get("dominant_pattern", "")
        if dominant in ("active_window_changed", "rapid_app_switching"):
            line = f"오 뭐 하는 거야? {remaining}초만 기다려, 곧 다시 올게!"
        elif dominant == "active_window_title_changed":
            line = f"앗 바꿨다! {remaining}초 뒤에 다시 놀러 올게~"
        elif dominant == "window_dwell_timeout":
            line = f"열심히 보고 있구나! {remaining}초 뒤에 다시 말 걸게 ㅎㅎ"
        elif dominant in ("system_idle_threshold",):
            line = f"어디 갔어...? {remaining}초 뒤에 다시 기다릴게~"
        elif dominant in ("frustration_pattern", "sigh_detected"):
            line = f"힘들어 보여... {remaining}초 뒤에 다시 올게, 잠깐 쉬어!"
        else:
            line = f"잠깐 쉬는 중이야~ {remaining}초 뒤에 돌아올게!"

        return {
            "대사": line,
            "표정": "편안",
            "위치": "활성창_오른쪽",
            "mood": current_mood,
            "message": line,
            "제안_메시지": "",
            "정답_내용": "",
        }

    @staticmethod
    def _parse(text: str, fallback_mood: str = "chill") -> dict:
        """Parse JSON from Gemini response, handling markdown wrapping and preamble text."""
        print(f"[boni brain] raw response: {text!r}")
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # LLM sometimes prepends text like "Here is the JSON requested:"
            # Try to extract a JSON object from within the response
            match = re.search(r"\{[^{}]*\}", text)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    return {"message": text[:80], "mood": fallback_mood}
            else:
                return {"message": text[:80], "mood": fallback_mood}
        if "message" not in parsed and "대사" in parsed:
            parsed["message"] = parsed["대사"]
        return parsed
