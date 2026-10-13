import re

TWEET_CHAR_LIMIT = 280
URL_PLACEHOLDER_LEN = 23
URL_PATTERN = re.compile(r"https?://\S+")


def count_chars(text: str) -> int:
    """Aproximacion pragmatica del conteo de caracteres de X.

    Reglas aplicadas (ver README para limitaciones conocidas):
    - Cada URL cuenta siempre como 23 caracteres (t.co shortening),
      sin importar su longitud real.
    - El resto del texto se cuenta por code point Unicode (len() en
      Python ya cuenta asi, a diferencia de JS que cuenta unidades UTF-16).
    """
    without_urls = URL_PATTERN.sub("", text)
    url_count = len(URL_PATTERN.findall(text))
    return len(without_urls) + url_count * URL_PLACEHOLDER_LEN


def within_limit(text: str) -> bool:
    return count_chars(text) <= TWEET_CHAR_LIMIT
