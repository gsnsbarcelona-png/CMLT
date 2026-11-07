"""Variedad de redaccion: cada pregunta/cierre fijo tiene alternativas, y se
elige una al azar evitando las ultimas usadas -- asi la cuenta no repite el
mismo texto semana tras semana y "regenerar" da un resultado distinto.

Solo se varian los cierres (preguntas y llamadas a la accion); los datos
(cifras, nombres, fechas) nunca se tocan. Las frases originales siguen siendo
una opcion mas del pool, no desaparecen."""

import random
from collections import deque

VARIETY_ENABLED = True  # los tests lo apagan para tener salidas deterministas
_RECENT_SIZE = 12
_recent: deque[str] = deque(maxlen=_RECENT_SIZE)

# pregunta original -> alternativas (tono neutro, sin voseo).
QUESTION_ALTERNATIVES: dict[str, list[str]] = {
    "¿A cuál prefieres tener en tu equipo?": ["¿Con cuál te quedarías en tu equipo?", "¿A cuál ficharías primero?"],
    "¿A cuál te gustaría tener en tu equipo?": ["¿Con cuál te quedarías en tu equipo?", "¿A cuál ficharías primero?"],
    "¿En qué elo estás tú?": ["¿Cuál es tu elo en soloQ?", "¿Cuántos de estos te ganarías en soloQ?"],
    "¿Alguien lo va a superar antes de que termine el split?": [
        "¿Alguien le arrebata ese puesto antes del final del split?",
        "¿Aguanta esa marca hasta el final del split?",
    ],
    "¿Es la clave de su temporada?": ["¿Es lo que está marcando su temporada?", "¿Será la clave de su split?"],
    "¿Eso alcanza para ganarle a las junglas rivales?": [
        "¿Le alcanza para mandar en la jungla?",
        "¿Es el mejor jungler de la liga ahora mismo?",
    ],
    "¿Puede sostener ese nivel bajo presión?": ["¿Lo mantiene cuando llegan los playoffs?", "¿Aguanta ese nivel hasta el final?"],
    "¿Quién le hace sombra?": ["¿Quién le puede discutir el puesto?", "¿Alguien le planta cara?"],
    "¿Quién le puede parar el paso?": ["¿Quién le frena?", "¿Hay alguien capaz de pararle?"],
    "¿Quién se lleva ese carril?": ["¿Quién gana el duelo de carril?", "¿Qué carril decide la serie?"],
    "¿Se cruzan antes de que termine el split?": ["¿Se ven las caras antes del final del split?", "¿Habrá cruce antes de acabar el split?"],
    "¿Se repite la historia la próxima vez que se crucen?": [
        "¿Se repite el resultado en el próximo cruce?",
        "¿Cambia la historia la próxima vez?",
    ],
    "¿Te animas a duelear contra él?": ["¿Te atreves a jugar contra el?", "¿Aceptarías el duelo?"],
    "¿Viste el clip?": ["¿Lo viste en directo?", "¿Se te escapó esta jugada?"],
    "¿Vuelve a ese nivel antes de que termine el split?": [
        "¿Recupera ese nivel antes del final del split?",
        "¿Lo veremos otra vez a ese nivel?",
    ],
    # H2H
    "¿Se repite la historia hoy?": ["¿Se repite el resultado hoy?", "¿Cambia la historia esta noche?"],
    "¿Quién llega mejor hoy?": ["¿Quién llega más en forma?", "¿A quién le sonríe el momento?"],
    # Cruce LEC
    "¿Se sostendría esa cifra en la LEC?": ["¿Esa cifra aguantaría en la LEC?", "¿Sería igual de buena en la LEC?"],
    "¿Aguantaría el ritmo LEC?": ["¿Estaría a la altura de la LEC?", "¿Daría el nivel de la LEC?"],
    # Top / ranking
    "¿Se mantiene arriba?": ["¿Seguirá liderando?", "¿Alguien le quita el puesto?"],
    "¿Se mantiene el top 1?": ["¿Cambia el liderato?", "¿Alguien destrona al primero?"],
    # Efemeride
    "¿Lo viviste en directo?": ["¿Dónde estabas tú cuando pasó?", "¿Te acuerdas de aquello?"],
}


def pick(options: list[str]) -> str:
    """Elige una opcion al azar evitando, si se puede, las usadas hace poco
    (memoria del proceso: se reinicia con el servidor)."""
    fresh = [o for o in options if o not in _recent]
    choice = random.choice(fresh or options)
    _recent.append(choice)
    return choice


def vary_question(question: str) -> str:
    """Devuelve `question` o una de sus alternativas. Si la pregunta no esta
    en la tabla (o la variedad esta apagada) queda tal cual. Conserva signos
    finales (emoji) que se pegan fuera: solo recibe la pregunta pura."""
    alternatives = QUESTION_ALTERNATIVES.get(question)
    if not VARIETY_ENABLED or not alternatives:
        return question
    return pick([question, *alternatives])


def choose(options: list[str]) -> str:
    """Como pick(), pero con la variedad apagada devuelve siempre la primera
    opcion (para cabeceras con varias redacciones posibles)."""
    return pick(options) if VARIETY_ENABLED else options[0]


def reset_recent() -> None:
    _recent.clear()
