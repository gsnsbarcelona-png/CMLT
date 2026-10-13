from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import auth_middleware
from app.auth import router as auth_router
from app.config import settings
from app.db import init_db
from app.routers import generate, templates, tweets


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Tweet Automation", lifespan=lifespan)
app.middleware("http")(auth_middleware)

app.include_router(auth_router)
app.include_router(tweets.router)
app.include_router(generate.router)
app.include_router(templates.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config/check")
def config_check() -> dict:
    return {
        "x_configured": settings.x_configured,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")


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
