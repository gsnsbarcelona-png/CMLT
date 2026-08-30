import tweepy

from app.config import settings


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


def publish_tweet(text: str) -> str:
    """Publica un tweet y devuelve el id devuelto por X.

    Levanta XPublishError con un mensaje en espanol listo para mostrar al
    usuario si algo falla; nunca deja pasar la excepcion cruda de tweepy.
    """
    if not settings.x_configured:
        raise XNotConfiguredError(
            "Faltan configurar las credenciales de X (X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET) en tu archivo .env."
        )

    client = get_x_client()
    try:
        response = client.create_tweet(text=text)
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
