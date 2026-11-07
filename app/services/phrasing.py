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
    "¿A cual prefieres tener en tu equipo?": ["¿Con cual te quedarias en tu equipo?", "¿A cual ficharias primero?"],
    "¿A cual te gustaria tener en tu equipo?": ["¿Con cual te quedarias en tu equipo?", "¿A cual ficharias primero?"],
    "¿En que elo estas tu?": ["¿Cual es tu elo en soloQ?", "¿Cuantos de estos te ganarias en soloQ?"],
    "¿Alguien lo va a superar antes de que termine el split?": [
        "¿Alguien le arrebata ese puesto antes del final del split?",
        "¿Aguanta esa marca hasta el final del split?",
    ],
    "¿Es la clave de su temporada?": ["¿Es lo que esta marcando su temporada?", "¿Sera la clave de su split?"],
    "¿Eso alcanza para ganarle a las junglas rivales?": [
        "¿Le alcanza para mandar en la jungla?",
        "¿Es el mejor jungler de la liga ahora mismo?",
    ],
    "¿Puede sostener ese nivel bajo presion?": ["¿Lo mantiene cuando llegan los playoffs?", "¿Aguanta ese nivel hasta el final?"],
    "¿Quien le hace sombra?": ["¿Quien le puede discutir el puesto?", "¿Alguien le planta cara?"],
    "¿Quien le puede parar el paso?": ["¿Quien le frena?", "¿Hay alguien capaz de pararle?"],
    "¿Quien se lleva ese carril?": ["¿Quien gana el duelo de carril?", "¿Que carril decide la serie?"],
    "¿Se cruzan antes de que termine el split?": ["¿Se ven las caras antes del final del split?", "¿Habra cruce antes de acabar el split?"],
    "¿Se repite la historia la proxima vez que se crucen?": [
        "¿Se repite el resultado en el proximo cruce?",
        "¿Cambia la historia la proxima vez?",
    ],
    "¿Te animas a duelear contra el?": ["¿Te atreves a jugar contra el?", "¿Aceptarias el duelo?"],
    "¿Viste el clip?": ["¿Lo viste en directo?", "¿Se te escapo esta jugada?"],
    "¿Vuelve a ese nivel antes de que termine el split?": [
        "¿Recupera ese nivel antes del final del split?",
        "¿Lo veremos otra vez a ese nivel?",
    ],
    # H2H
    "¿Se repite la historia hoy?": ["¿Se repite el resultado hoy?", "¿Cambia la historia esta noche?"],
    "¿Quien llega mejor hoy?": ["¿Quien llega mas en forma?", "¿A quien le sonrie el momento?"],
    # Cruce LEC
    "¿Se sostendria esa cifra en la LEC?": ["¿Esa cifra aguantaria en la LEC?", "¿Seria igual de buena en la LEC?"],
    "¿Aguantaria el ritmo LEC?": ["¿Estaria a la altura de la LEC?", "¿Daria el nivel de la LEC?"],
    # Top / ranking
    "¿Se mantiene arriba?": ["¿Seguira liderando?", "¿Alguien le quita el puesto?"],
    "¿Se mantiene el top 1?": ["¿Cambia el liderato?", "¿Alguien destrona al primero?"],
    # Efemeride
    "¿Lo viviste en directo?": ["¿Donde estabas tu cuando paso?", "¿Te acuerdas de aquello?"],
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
