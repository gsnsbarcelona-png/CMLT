"""Login de un solo usuario con contraseña (APP_PASSWORD).

Si APP_PASSWORD esta vacia la proteccion queda desactivada (uso local, como
siempre). Si esta cargada, toda la API (salvo health y login) y la pagina
principal piden una sesion valida: una cookie HttpOnly firmada con HMAC que
guarda solo la fecha de expiracion. La clave de la firma mezcla SESSION_SECRET
con la contraseña, asi cambiar la contraseña invalida todas las sesiones."""

import hashlib
import hmac
import logging
import secrets
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ta_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600

# Rutas accesibles sin sesion: login (pagina y API), health, y lo que el
# navegador necesita para mostrar la pagina de login / instalar la PWA.
PUBLIC_PATHS = {
    "/login",
    "/api/auth/login",
    "/api/auth/status",
    "/api/health",
    "/sw.js",
    "/.well-known/assetlinks.json",
}
PUBLIC_PREFIXES = ("/static/",)

# Limite de intentos fallidos por IP: tras MAX_FAILED_LOGINS fallos dentro de
# la ventana, esa IP queda bloqueada hasta que la ventana se agote. En memoria
# (se reinicia con el server), suficiente para una app de un solo usuario.
MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
_failed_logins: dict[str, list[float]] = {}
_failed_logins_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_failures(ip: str, now: float) -> list[float]:
    recent = [t for t in _failed_logins.get(ip, []) if now - t < FAILED_LOGIN_WINDOW_SECONDS]
    if recent:
        _failed_logins[ip] = recent
    else:
        _failed_logins.pop(ip, None)
    return recent

if settings.session_secret:
    _secret = settings.session_secret.encode()
else:
    # Sin SESSION_SECRET las sesiones se pierden al reiniciar el server, pero
    # sigue siendo seguro (la clave nunca sale del proceso).
    _secret = secrets.token_bytes(32)
    if settings.app_password:
        logger.warning("SESSION_SECRET no configurado: las sesiones se pierden al reiniciar el server")


def auth_enabled() -> bool:
    return bool(settings.app_password)


def _signing_key() -> bytes:
    return hashlib.sha256(_secret + b"\0" + settings.app_password.encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + SESSION_TTL_SECONDS)
    return f"{expires}.{_sign(str(expires))}"


def is_valid_session_token(token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    expires, signature = token.split(".", 1)
    if not expires.isdigit() or not hmac.compare_digest(signature, _sign(expires)):
        return False
    return int(expires) > (now if now is not None else time.time())


def is_authenticated(request: Request) -> bool:
    return not auth_enabled() or is_valid_session_token(request.cookies.get(SESSION_COOKIE))


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


async def auth_middleware(request: Request, call_next):
    if is_authenticated(request) or _is_public(request.url.path):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Sesion no iniciada o expirada."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.get("/status")
def auth_status(request: Request) -> dict:
    return {"enabled": auth_enabled(), "authenticated": is_authenticated(request)}


@router.post("/login", status_code=204)
def login(payload: LoginRequest, request: Request, response: Response) -> None:
    if not auth_enabled():
        return
    ip = _client_ip(request)
    now = time.time()
    with _failed_logins_lock:
        recent = _recent_failures(ip, now)
        if len(recent) >= MAX_FAILED_LOGINS:
            retry_after = int(FAILED_LOGIN_WINDOW_SECONDS - (now - recent[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos fallidos. Espera unos minutos y vuelve a probar.",
                headers={"Retry-After": str(retry_after)},
            )
    if not hmac.compare_digest(payload.password.encode(), settings.app_password.encode()):
        with _failed_logins_lock:
            _failed_logins.setdefault(ip, []).append(now)
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    with _failed_logins_lock:
        _failed_logins.pop(ip, None)
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # Detras de un proxy HTTPS (Render, Fly...) uvicorn tiene que correr con
        # --proxy-headers para que el esquema se vea como https aca.
        secure=request.url.scheme == "https",
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
