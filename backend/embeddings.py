"""Vertex AI embedding generation and text composition."""

from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel


# Singleton model instance
_model: TextEmbeddingModel | None = None


def _get_model() -> TextEmbeddingModel:
    global _model
    if _model is None:
        _model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    return _model


def compose_embedding_text(metrics: dict, reaction: dict) -> str:
    """Compose a natural language summary from metrics + reaction for semantic search.

    Instead of embedding raw JSON numbers, we create human-readable text
    so that vector search can match patterns like "late night coding" or
    "high CPU while gaming".
    """
    hour = metrics.get("hour", 0)
    minute = metrics.get("minute", 0)

    # Time description
    if 5 <= hour < 12:
        time_desc = f"오전 {hour}시 {minute:02d}분, 아침/오전 시간"
    elif 12 <= hour < 18:
        time_desc = f"오후 {hour - 12 if hour > 12 else 12}시 {minute:02d}분, 낮/오후 시간"
    elif 18 <= hour < 23:
        time_desc = f"저녁 {hour - 12}시 {minute:02d}분, 저녁 시간"
    else:
        time_desc = f"새벽/밤 {hour}시 {minute:02d}분, 늦은 밤"

    # CPU description
    cpu = metrics.get("cpu_percent", 0)
    if cpu > 80:
        cpu_desc = f"CPU {cpu}%, 매우 높은 부하"
    elif cpu > 50:
        cpu_desc = f"CPU {cpu}%, 중간 부하"
    else:
        cpu_desc = f"CPU {cpu}%, 낮은 부하"

    # RAM description
    ram = metrics.get("ram_percent", 0)
    if ram > 85:
        ram_desc = f"RAM {ram}%, 메모리 거의 가득 참"
    elif ram > 60:
        ram_desc = f"RAM {ram}%, 메모리 적당히 사용 중"
    else:
        ram_desc = f"RAM {ram}%, 메모리 여유 있음"

    # Battery description
    battery = metrics.get("battery_percent")
    charging = metrics.get("is_charging", False)
    if battery is not None:
        charge_str = " (충전 중)" if charging else ""
        if battery < 15:
            battery_desc = f"배터리 {battery}%{charge_str}, 거의 방전"
        elif battery < 50:
            battery_desc = f"배터리 {battery}%{charge_str}, 낮은 편"
        else:
            battery_desc = f"배터리 {battery}%{charge_str}"
    else:
        battery_desc = "데스크톱 Mac, 항상 전원 연결"

    # App context
    app = metrics.get("active_app", "Unknown")
    app_count = metrics.get("running_apps", 0)
    app_desc = f"{app}을(를) 사용 중, 총 {app_count}개 앱 실행"

    # Reaction
    mood = reaction.get("mood", "chill")
    message = reaction.get("message", "")

    text = (
        f"{time_desc}. {app_desc}. "
        f"{cpu_desc}. {ram_desc}. {battery_desc}. "
        f"boni 기분: {mood}. 반응: \"{message}\""
    )
    return text


def generate_embedding(text: str) -> list[float]:
    """Generate a 768-dimensional embedding vector from text."""
    model = _get_model()
    embeddings = model.get_embeddings(
        [text],
        output_dimensionality=768,
    )
    return embeddings[0].values
