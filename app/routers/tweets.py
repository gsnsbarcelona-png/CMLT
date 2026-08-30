from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Tweet
from app.services import char_count
from app.services.x_service import XPublishError, publish_tweet

router = APIRouter(prefix="/api/tweets", tags=["tweets"])


class TweetCreate(BaseModel):
    content: str
    source: str = "manual"


class TweetUpdate(BaseModel):
    content: str


@router.post("", status_code=201)
def create_tweet(payload: TweetCreate, session: Session = Depends(get_session)) -> Tweet:
    tweet = Tweet(
        content=payload.content,
        source=payload.source,
        char_count=char_count.count_chars(payload.content),
    )
    session.add(tweet)
    session.commit()
    session.refresh(tweet)
    return tweet


@router.get("")
def list_tweets(status: str | None = None, session: Session = Depends(get_session)) -> list[Tweet]:
    query = select(Tweet)
    if status:
        query = query.where(Tweet.status == status)
    query = query.order_by(Tweet.created_at.desc())
    return list(session.exec(query))


@router.get("/{tweet_id}")
def get_tweet(tweet_id: int, session: Session = Depends(get_session)) -> Tweet:
    tweet = session.get(Tweet, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet no encontrado.")
    return tweet


@router.put("/{tweet_id}")
def update_tweet(tweet_id: int, payload: TweetUpdate, session: Session = Depends(get_session)) -> Tweet:
    tweet = session.get(Tweet, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet no encontrado.")
    if tweet.status != "draft":
        raise HTTPException(status_code=409, detail="Solo se pueden editar borradores.")
    tweet.content = payload.content
    tweet.char_count = char_count.count_chars(payload.content)
    session.add(tweet)
    session.commit()
    session.refresh(tweet)
    return tweet


@router.delete("/{tweet_id}", status_code=204)
def delete_tweet(tweet_id: int, session: Session = Depends(get_session)) -> None:
    tweet = session.get(Tweet, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet no encontrado.")
    if tweet.status == "published":
        raise HTTPException(status_code=409, detail="No se puede borrar un tweet ya publicado.")
    session.delete(tweet)
    session.commit()


@router.post("/{tweet_id}/publish")
def publish(tweet_id: int, session: Session = Depends(get_session)) -> Tweet:
    tweet = session.get(Tweet, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet no encontrado.")
    if tweet.status == "published":
        raise HTTPException(status_code=409, detail="Este tweet ya fue publicado.")

    current_count = char_count.count_chars(tweet.content)
    if current_count > char_count.TWEET_CHAR_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"El tweet supera el limite de {char_count.TWEET_CHAR_LIMIT} caracteres ({current_count}).",
        )

    try:
        remote_id = publish_tweet(tweet.content)
    except XPublishError as exc:
        tweet.status = "failed"
        tweet.error_message = str(exc)
        session.add(tweet)
        session.commit()
        session.refresh(tweet)
        return tweet

    tweet.status = "published"
    tweet.tweet_id = remote_id
    tweet.published_at = datetime.now(timezone.utc)
    tweet.error_message = None
    session.add(tweet)
    session.commit()
    session.refresh(tweet)
    return tweet


@router.post("/{tweet_id}/retry")
def retry(tweet_id: int, session: Session = Depends(get_session)) -> Tweet:
    tweet = session.get(Tweet, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet no encontrado.")
    if tweet.status != "failed":
        raise HTTPException(status_code=409, detail="Solo se pueden reintentar tweets fallidos.")
    tweet.status = "draft"
    tweet.error_message = None
    session.add(tweet)
    session.commit()
    session.refresh(tweet)
    return tweet
