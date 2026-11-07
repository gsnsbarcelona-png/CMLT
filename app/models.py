from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tweet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    status: str = Field(default="draft")  # draft | published | failed
    source: str = Field(default="manual")  # modo de Compose que lo genero (calendar, stats, manual...)
    char_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: Optional[datetime] = None
    tweet_id: Optional[str] = None
    error_message: Optional[str] = None
    image_url: Optional[str] = None  # ruta propia ("/data/images/...") o URL externa (escudo de lolesports.com)
