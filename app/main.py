import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import auth_middleware
from app.auth import router as auth_router
from app.config import settings
from app.db import init_db
from app.routers import generate, images, templates, tweets
from app.routers.images import IMAGES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En Render (que define RENDER=true) la app es publica: sin contrasena
    # cualquiera podria usar la API, asi que mejor no arrancar.
    if os.environ.get("RENDER") and not settings.app_password:
        raise RuntimeError("APP_PASSWORD no esta configurada: la app es publica en Render y quedaria abierta.")
    init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Tweet Automation", lifespan=lifespan)
app.middleware("http")(auth_middleware)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response

app.include_router(auth_router)
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
        "x_configured": settings.x_configured,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data/images", StaticFiles(directory=str(IMAGES_DIR), check_dir=False), name="images")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse("static/login.html")


# El service worker se sirve desde la raiz (y no desde /static/) para que su
# alcance cubra toda la app.
@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse("static/sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


# Verificacion de dominio para el APK generado con Bubblewrap (Trusted Web
# Activity): sin este archivo el APK muestra la barra de URL de Chrome.
@app.get("/.well-known/assetlinks.json")
def asset_links() -> FileResponse:
    path = Path("static/well-known/assetlinks.json")
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="application/json")
