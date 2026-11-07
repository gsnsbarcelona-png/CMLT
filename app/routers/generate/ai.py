from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, _result
from app.services import char_count
from app.services.ai_service import AIGenerationError, generate_tweet

router = APIRouter()

MAX_BATCH_TOPICS = 25


class AIGenerateRequest(BaseModel):
    topic: str
    tone: str | None = None
    instructions: str | None = None


@router.post("/ai")
def generate_ai(payload: AIGenerateRequest) -> GenerateResult:
    try:
        content = generate_tweet(payload.topic, payload.tone, payload.instructions)
    except AIGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _result(content)


class BatchGenerateRequest(BaseModel):
    topics: list[str]
    tone: str | None = None
    instructions: str | None = None


class BatchTopicResult(BaseModel):
    topic: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None


@router.post("/ai/batch")
def generate_ai_batch(payload: BatchGenerateRequest) -> list[BatchTopicResult]:
    topics = [t.strip() for t in payload.topics if t.strip()]
    if not topics:
        raise HTTPException(status_code=400, detail="Ingresa al menos un tema.")
    if len(topics) > MAX_BATCH_TOPICS:
        raise HTTPException(status_code=400, detail=f"Maximo {MAX_BATCH_TOPICS} temas por lote.")

    results: list[BatchTopicResult] = []
    for topic in topics:
        try:
            content = generate_tweet(topic, payload.tone, payload.instructions)
        except AIGenerationError as exc:
            results.append(BatchTopicResult(topic=topic, error=str(exc)))
            continue

        count = char_count.count_chars(content)
        results.append(
            BatchTopicResult(
                topic=topic,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
            )
        )
    return results
