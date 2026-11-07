import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session

from app.auth import auth_middleware
from app.auth import router as auth_router
from app.config import settings
from app.db import engine, init_db
from app.routers import backup, generate, images, tweets
from app.routers.images import IMAGES_DIR
from app.version import router as version_router


def _prewarm() -> None:
    """Calienta las caches en segundo plano sin bloquear el arranque ni
    romperlo si una fuente esta caida."""
    from app.services import golgg_service, lolesports_service

    golgg_service.prewarm()
    try:
        lolesports_service._fetch_all_teams()
    except Exception:
        logger.warning("Precalentamiento de lolesports fallo (no es grave)", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En Render (que define RENDER=true) la app es publica: sin contrasena
    # cualquiera podria usar la API, asi que mejor no arrancar.
    if os.environ.get("RENDER") and not settings.app_password:
        raise RuntimeError("APP_PASSWORD no esta configurada: la app es publica en Render y quedaria abierta.")
    init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if settings.prewarm_cache:
        threading.Thread(target=_prewarm, daemon=True, name="prewarm").start()
    yield


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

app = FastAPI(title="Tweet Automation", lifespan=lifespan)
app.middleware("http")(auth_middleware)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    if response.status_code >= 500:
        # Los errores de las fuentes (gol.gg, lolesports, lolpros) llegan aqui
        # como 502 con un mensaje para el usuario; sin esto no quedaria rastro
        # en los logs de Render de que paso ni en que ruta.
        logger.warning("%s %s -> %s", request.method, request.url.path, response.status_code)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response

app.include_router(auth_router)
app.include_router(version_router)
app.include_router(tweets.router)
app.include_router(generate.router)
app.include_router(images.router)
app.include_router(backup.router)


@app.get("/api/health")
def health() -> dict:
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: la base de datos no responde")
        raise HTTPException(status_code=503, detail="Base de datos no disponible.")
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
