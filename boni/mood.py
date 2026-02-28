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
    Mood.CHILL: "🦝",
    Mood.STUFFED: "😮",
    Mood.OVERHEATED: "🥵",
    Mood.DYING: "😢",
    Mood.SUSPICIOUS: "🧐",
    Mood.JUDGY: "😏",
    Mood.PLEASED: "😊",
    Mood.NOCTURNAL: "😴",
}

# Default messages before AI kicks in
DEFAULT_MESSAGES = {
    Mood.CHILL: "안녕~ 나 boni야! 오늘도 같이 놀자 🦝",
    Mood.STUFFED: "우와 여기 뭐가 이렇게 많아~ 복잡복잡!",
    Mood.OVERHEATED: "헥헥... 여기 왜 이렇게 더워 ㅠㅠ",
    Mood.DYING: "으앙... 힘들어... 충전해줘...!",
    Mood.SUSPICIOUS: "오? 뭐 하는 거야~ 나도 보여줘!",
    Mood.JUDGY: "에헤헤~ 지금 이거 보는 거야? ㅎㅎ",
    Mood.PLEASED: "와~ 깔끔하다! 기분 좋아~",
    Mood.NOCTURNAL: "쿨쿨... 아직 안 자? 나는 졸려...",
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
