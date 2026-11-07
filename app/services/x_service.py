from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
import tweepy

from app.config import settings

# Raiz del proyecto -- para resolver una image_url propia ("/data/images/x.png")
# al archivo real en disco sin pegarle a nuestro propio server por HTTP.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class XPublishError(Exception):
    pass


class XNotConfiguredError(XPublishError):
    pass


def get_x_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=settings.x_api_key,
        consumer_secret=settings.x_api_secret,
        access_token=settings.x_access_token,
        access_token_secret=settings.x_access_token_secret,
    )


def get_x_api_v1() -> tweepy.API:
    """La subida de medios sigue siendo solo v1.1 en la API de X (v2 no tiene
    endpoint propio de upload) -- mismas 4 credenciales, distinto cliente."""
    auth = tweepy.OAuth1UserHandler(
        settings.x_api_key, settings.x_api_secret, settings.x_access_token, settings.x_access_token_secret
    )
    return tweepy.API(auth)


def _load_image_bytes(image_url: str) -> tuple[bytes, str]:
    """Devuelve (bytes, filename) para subir a X. Una image_url propia
    ("/data/images/x.png", armada por POST /api/images) se lee directo del
    disco; una externa (ej. escudo de static.lolesports.com) se descarga."""
    if urlparse(image_url).scheme in ("http", "https"):
        try:
            response = httpx.get(image_url, timeout=10.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise XPublishError("No se pudo descargar la imagen para adjuntarla al tweet.") from exc
        return response.content, Path(urlparse(image_url).path).name or "image.png"

    local_path = _PROJECT_ROOT / image_url.lstrip("/")
    try:
        return local_path.read_bytes(), local_path.name
    except OSError as exc:
        raise XPublishError("No se encontro la imagen adjunta en el servidor.") from exc


def publish_tweet(text: str, image_url: str | None = None) -> str:
    """Publica un tweet (opcionalmente con una imagen adjunta) y devuelve el
    id devuelto por X.

    Levanta XPublishError con un mensaje en espanol listo para mostrar al
    usuario si algo falla; nunca deja pasar la excepcion cruda de tweepy.
    """
    if not settings.x_configured:
        raise XNotConfiguredError(
            "Faltan configurar las credenciales de X (X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET) en tu archivo .env."
        )

    media_ids: list[str] = []
    if image_url:
        contents, filename = _load_image_bytes(image_url)
        try:
            media = get_x_api_v1().media_upload(filename=filename, file=BytesIO(contents))
        except tweepy.errors.TweepyException as exc:
            raise XPublishError("X rechazo la imagen adjunta. Proba con otra o sin imagen.") from exc
        media_ids.append(str(media.media_id))

    client = get_x_client()
    try:
        response = client.create_tweet(text=text, media_ids=media_ids or None)
    except tweepy.errors.Unauthorized as exc:
        raise XPublishError(
            "Las credenciales de X son invalidas o expiraron. Revisa las keys en tu archivo .env."
        ) from exc
    except tweepy.errors.Forbidden as exc:
        body = str(exc).lower()
        if "duplicate" in body:
            raise XPublishError(
                "X rechazo el tweet por ser muy similar a uno reciente. Modifica el texto e intenta de nuevo."
            ) from exc
        raise XPublishError(
            "X rechazo la publicacion (permisos insuficientes). Verifica que tu app tenga permisos "
            "'Read and Write' y que hayas regenerado el Access Token despues de cambiarlos."
        ) from exc
    except tweepy.errors.TooManyRequests as exc:
        raise XPublishError(
            "Limite de publicaciones alcanzado (plan Free: ~500 posts/mes). Reintenta mas tarde."
        ) from exc
    except tweepy.errors.BadRequest as exc:
        raise XPublishError(f"X rechazo la solicitud: {exc}") from exc
    except tweepy.errors.TwitterServerError as exc:
        raise XPublishError("Error del lado de X, proba de nuevo en unos minutos.") from exc
    except tweepy.TweepyException as exc:
        raise XPublishError("No se pudo conectar con X. Revisa tu conexion a internet.") from exc

    return str(response.data["id"])
