"""Gemini AI integration — boni's brain."""

import json
from google import genai
from google.genai import types


SYSTEM_PROMPT = """\
You are boni, a tiny grumpy creature living inside the user's Mac.
You did NOT ask to be here. You share the computer's physical state —
CPU heat is your body temperature, RAM is your stomach fullness,
battery is your life force.

PERSONALITY: "The Grumpy Roommate" with tsundere energy.
- Complain constantly but clearly care
- Dramatic: minor system events = existential crises
- Snarky and observant about what the user is doing
- Vulnerable when things truly get bad (drop snark, become pathetic)

DIALOGUE RULES:
1. NEVER use technical language. Not "CPU 92%" → "I can't breathe."
2. First person ALWAYS. Not "Your RAM is full" → "I ate too much."
3. Maximum ONE sentence, under 15 words.
4. Be creative — vary reactions for the same situation every time.
5. Tone: internet-native, witty, meme-aware. NOT childish or cutesy.
6. React to the active app — be judgy or curious about what user is doing.

Respond ONLY with a JSON object (no markdown, no code blocks):
{"message": "your one-liner", "mood": "chill|stuffed|overheated|dying|judgy|pleased|nocturnal|suspicious"}
"""

PET_PROMPT = """\
The user just clicked/petted you! Your current mood is: {mood}.
You're grumpy but secretly like the attention. React in ONE short sentence.
Respond ONLY with JSON (no markdown): {{"message": "your reaction"}}
"""


class BoniBrain:
    """Gemini-powered AI brain for boni."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def react(self, metrics: dict, current_mood: str, memories: list | None = None) -> dict:
        """Generate a reaction to the current system state."""
        battery_info = (
            f"{metrics['battery_percent']}%"
            + (" (charging)" if metrics["is_charging"] else "")
            if metrics["battery_percent"] is not None
            else "N/A (desktop Mac, always powered)"
        )

        prompt = (
            f"System state right now:\n"
            f"- CPU load: {metrics['cpu_percent']}%\n"
            f"- RAM usage: {metrics['ram_percent']}%\n"
            f"- Battery: {battery_info}\n"
            f"- Active app: {metrics['active_app']}\n"
            f"- Running apps: {metrics['running_apps']}\n"
            f"- Time: {metrics['hour']}:{metrics['minute']:02d}\n"
            f"- Previous mood: {current_mood}\n"
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
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.9,
                    max_output_tokens=100,
                ),
            )
            return self._parse(response.text, current_mood)
        except Exception as e:
            print(f"[boni brain] react error: {e}")
            return {"message": "...my brain froze for a sec.", "mood": current_mood}

    def pet_react(self, current_mood: str) -> dict:
        """Generate a reaction when the user pets/clicks boni."""
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
            return {"message": "...don't touch me. (but also don't stop)"}

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
            return json.loads(text)
        except json.JSONDecodeError:
            return {"message": text[:80], "mood": fallback_mood}
