"""Mood/emotion model for boni."""

from enum import Enum


class Mood(Enum):
    CHILL = "chill"
    STUFFED = "stuffed"
    OVERHEATED = "overheated"
    DYING = "dying"
    SUSPICIOUS = "suspicious"
    JUDGY = "judgy"
    PLEASED = "pleased"
    NOCTURNAL = "nocturnal"


# Emoji shown in menu bar and floating window
MOOD_EMOJI = {
    Mood.CHILL: "😌",
    Mood.STUFFED: "😤",
    Mood.OVERHEATED: "🥵",
    Mood.DYING: "💀",
    Mood.SUSPICIOUS: "👀",
    Mood.JUDGY: "😒",
    Mood.PLEASED: "☺️",
    Mood.NOCTURNAL: "😴",
}

# Default messages before AI kicks in
DEFAULT_MESSAGES = {
    Mood.CHILL: "Just moved in. Nice Mac you got.",
    Mood.STUFFED: "I just got here and it's already crowded...",
    Mood.OVERHEATED: "Is it always this hot in here?!",
    Mood.DYING: "I arrived just in time to watch us both die.",
    Mood.SUSPICIOUS: "...what are you up to?",
    Mood.JUDGY: "So this is what you do all day?",
    Mood.PLEASED: "Oh, nice. We're organized today.",
    Mood.NOCTURNAL: "You're still awake? ...I guess I am too now.",
}


def determine_mood(metrics: dict) -> Mood:
    """Determine boni's mood from system metrics. Priority-based."""
    cpu = metrics.get("cpu_percent", 0)
    ram = metrics.get("ram_percent", 0)
    battery = metrics.get("battery_percent")
    is_charging = metrics.get("is_charging", True)
    is_late_night = metrics.get("is_late_night", False)
    is_work_hours = metrics.get("is_work_hours", False)
    active_app = (metrics.get("active_app") or "").lower()

    # 1. Critical: battery dying
    if battery is not None and battery < 15 and not is_charging:
        return Mood.DYING

    # 2. Late night
    if is_late_night:
        return Mood.NOCTURNAL

    # 3. CPU on fire
    if cpu > 80:
        return Mood.OVERHEATED

    # 4. RAM stuffed
    if ram > 85:
        return Mood.STUFFED

    # 5. Just plugged in charger — relieved
    if is_charging and battery is not None and battery < 50:
        return Mood.PLEASED

    # 6. Entertainment during work hours — judgy
    entertainment = [
        "youtube", "netflix", "twitch", "tiktok",
        "reddit", "twitter", "instagram", "discord",
    ]
    if is_work_hours and any(app in active_app for app in entertainment):
        return Mood.JUDGY

    # 7. Default: chill
    return Mood.CHILL
