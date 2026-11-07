import base64
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import generate, images, templates, tweets
from app.routers.images import IMAGES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Tweet Automation", lifespan=lifespan)

@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if not settings.app_password or request.url.path == "/api/health":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            _, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except Exception:
            password = ""
        if secrets.compare_digest(password.encode(), settings.app_password.encode()):
            return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Tweet Automation"'})


app.include_router(tweets.router)
app.include_router(generate.router)
app.include_router(templates.router)
app.include_router(images.router)


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
app.mount("/data/images", StaticFiles(directory=str(IMAGES_DIR), check_dir=False), name="images")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")
