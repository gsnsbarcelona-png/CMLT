"""Copia de seguridad en JSON de borradores e historial.

Pensado para el plan gratuito de Render (disco efimero): se descarga el JSON
antes de un cambio importante y se restaura despues. Las imagenes subidas no
van en la copia (son archivos del disco); si una image_url propia ya no existe
tras restaurar, el tweet queda igual pero sin imagen valida. Una copia antigua
con la clave "templates" (de cuando existian las plantillas) se acepta e ignora."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Tweet
from app.services.image_urls import is_allowed_image_url

router = APIRouter(prefix="/api", tags=["backup"])

BACKUP_VERSION = 1


class TweetBackup(BaseModel):
    content: str
    status: str = "draft"
    source: str = "manual"
    char_count: int = 0
    created_at: datetime | None = None
    published_at: datetime | None = None
    tweet_id: str | None = None
    error_message: str | None = None
    image_url: str | None = None


class BackupFile(BaseModel):
    version: int = BACKUP_VERSION
    exported_at: datetime | None = None
    tweets: list[TweetBackup] = []


@router.get("/backup")
def export_backup(session: Session = Depends(get_session)) -> BackupFile:
    tweets = session.exec(select(Tweet).order_by(Tweet.id)).all()
    return BackupFile(
        exported_at=datetime.now(timezone.utc),
        tweets=[TweetBackup(**t.model_dump(exclude={"id"})) for t in tweets],
    )


@router.post("/restore")
def restore_backup(payload: BackupFile, session: Session = Depends(get_session)) -> dict:
    """Mezcla la copia con lo que ya hay: se salta los tweets (mismo texto y
    fecha de creacion) que ya existen, asi restaurar dos veces no duplica nada."""
    existing = {(t.content, _naive(t.created_at)) for t in session.exec(select(Tweet)).all()}

    added = 0
    for item in payload.tweets:
        key = (item.content, _naive(item.created_at))
        if key in existing:
            continue
        data = item.model_dump(exclude_none=True)
        image_url = data.get("image_url")
        if image_url and not is_allowed_image_url(image_url):
            data.pop("image_url")
        session.add(Tweet(**data))
        existing.add(key)
        added += 1
    session.commit()
    return {"tweets_added": added}


def _naive(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=None) if value is not None else None
