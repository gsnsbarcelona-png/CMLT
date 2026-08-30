from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import generate, templates, tweets


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Tweet Automation", lifespan=lifespan)

app.include_router(tweets.router)
app.include_router(generate.router)
app.include_router(templates.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config/check")
def config_check() -> dict:
    return {
        "anthropic_configured": settings.anthropic_configured,
        "x_configured": settings.x_configured,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")
