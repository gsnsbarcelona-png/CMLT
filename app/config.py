import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""

    lolesports_api_key: str = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"

    # Hay que actualizar estos 3 en cada split nuevo (buscar el nombre exacto
    # del torneo en gol.gg, ej. https://gol.gg/tournament/tournament-stats/LES%202026%20Summer/)
    # Con autodiscover activo (por defecto) la temporada y los torneos de
    # abajo se descubren solos desde gol.gg (cache de unas horas); los valores
    # de abajo quedan como respaldo si gol.gg no responde. Ponlo en false
    # para forzar a mano los valores configurados.
    golgg_autodiscover: bool = True
    # Calienta la cache de gol.gg/lolesports en segundo plano al arrancar.
    prewarm_cache: bool = True
    golgg_season: str = "S16"
    golgg_tournament: str = "LES 2026 Summer"
    # Torneos que forman "todo el año" para el scope=year de Stats (separados por
    # coma) -- incluye playoffs para capturar rivalidades que se cruzaron mas de
    # una vez en la temporada regular (ej. en la fase de grupos de cada split) y
    # otra vez en playoffs.
    golgg_year_tournaments: str = (
        "LES 2026 Kick-off Tournament,LES 2026 Spring,LES 2026 Spring Playoffs,"
        "LES 2026 Summer,LES 2026 Summer Playoffs"
    )
    # Para comparativas LES-LEC (Stats -> "Cruce LEC"). Ojo: en gol.gg el
    # nombre completo de la LEC lleva "Season" al final, a diferencia de LES.
    lec_tournament: str = "LEC 2026 Summer Season"
    # Torneos de EMEA Masters en gol.gg (separados por coma) -- un equipo de
    # LES que juega ahi se cruza con rivales que nunca jugaron en LES, asi
    # que H2H necesita esta lista aparte para tener forma reciente/historial
    # de esos cruces. Igual que GOLGG_YEAR_TOURNAMENTS, hay que actualizarla
    # a mano en cada split nuevo de EMEA Masters (buscar el nombre exacto con
    # GET /api/generate/stats/available-tournaments?region=WR).
    emea_masters_tournaments: str = (
        "EMEA Masters 2026 Winter,EMEA Masters 2026 Spring Play-In,EMEA Masters 2026 Spring Main Event"
    )

    # Arrobas/hashtags que se agregan al final de los tweets generados.
    league_handle_les: str = "@LESESPORTS"
    league_handle_lec: str = "@LEC"
    league_handle_emea_masters: str = "@EMEAmasters"
    custom_hashtags: str = "#LT"
    # "Nombre de equipo:@handle" separados por coma -- solo se usan en Stats
    # (en Calendario arrobar a todos los equipos de todos los partidos saturaria
    # el texto). Cargados a mano, no adivinados. UB Alma Mater queda afuera a
    # proposito: se probaron @UniBarcelona (cuenta general de la universidad)
    # y @EsportsUB (que resulto ser el Servei d'Esports general, no el equipo
    # de LoL) y ninguno de los dos es correcto -- mejor no arrobar a nadie.
    team_handles: str = (
        "Barca eSports:@FCBeSports,"
        "Falke Esports:@FALKE_EC,"
        "GIANTX iTero:@GIANTXLeague,"
        "LUA Gaming:@LUAGaming_,"
        "Movistar KOI Fenix:@MovistarKOILoL,"
        "Team Heretics Academy:@HereticsLES,"
        "UCAM Esports:@UCAM_esports"
    )

    # Login: con APP_PASSWORD vacia la app no pide contraseña (uso local). Para
    # exponerla en internet (ej. usarla desde el movil) hay que cargarla, y
    # conviene fijar SESSION_SECRET para que las sesiones sobrevivan reinicios.
    app_password: str = ""
    session_secret: str = ""

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/tweets.db"

    @property
    def custom_hashtag_list(self) -> list[str]:
        return [h.strip() for h in self.custom_hashtags.split() if h.strip()]

    @property
    def x_configured(self) -> bool:
        return bool(self.x_api_key and self.x_api_secret and self.x_access_token and self.x_access_token_secret)


settings = Settings()

if not settings.x_configured:
    logger.warning("Credenciales de X incompletas: la publicacion no va a funcionar hasta que las cargues en .env")
