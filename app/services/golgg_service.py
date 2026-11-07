"""Fachada de compatibilidad: la implementacion vive en el paquete
app.services.golgg (client, config, models, stats, h2h, candidates,
league_comparison, top_ranking, formatters). Este modulo reexporta los
nombres que usan routers, otros servicios y tests.

Ojo al parchear en tests: hay que hacerlo en el modulo donde el nombre se USA
(p.ej. app.services.golgg.client._cached_get), no aqui."""
import httpx  # noqa: F401  (los tests parchean golgg_service.httpx.get/post)

from app.config import settings  # noqa: F401
from app.services.golgg.candidates import (  # noqa: F401
    TEAM_LEVEL_KINDS,
    compute_candidates,
    get_team_handles,
    pick_candidate,
    stat_closing_tags,
)
from app.services.golgg.client import (  # noqa: F401
    GOLGG_BASE,
    GOLGG_HEADERS,
    _cached_get,
    _fetch_table,
    _http_cache,
    _parse_table,
    _real_warm_urls,
    warm_urls,
)
from app.services.golgg.config import (  # noqa: F401
    discover_tournaments,
    get_active_config,
    get_current_tournament,
    get_emea_masters_tournaments,
    get_lec_tournament,
    get_year_tournaments,
    reset_active_config_cache,
)
from app.services.golgg.formatters import (  # noqa: F401
    format_h2h_variant_plain,
    format_league_comparison_plain,
    format_stat_tweet_plain,
    format_top_ranking_plain,
)
from app.services.golgg.h2h import (  # noqa: F401
    _recent_form,
    build_head_to_head_preview,
    compute_head_to_head_candidates,
    fetch_all_match_results,
    fetch_match_results,
    find_head_to_head,
)
from app.services.golgg.league_comparison import (  # noqa: F401
    LEVEL_NUANCE,
    compute_league_comparison_candidates,
    pick_league_comparison_candidate,
)
from app.services.golgg.models import (  # noqa: F401
    ActiveConfig,
    GolGGError,
    HeadToHeadPreviewData,
    LeagueComparisonCandidate,
    MatchResult,
    PlayerStat,
    RecentForm,
    StatCandidate,
    StatFocusNotFoundError,
    TeamStat,
    TopRankingCandidate,
    TopRankingEntry,
)
from app.services.golgg.stats import (  # noqa: F401
    _tournament_path,
    aggregate_player_stats,
    aggregate_team_stats,
    fetch_player_stats,
    fetch_team_stats,
    prewarm,
    warm_stats_pages,
)
from app.services.golgg.top_ranking import (  # noqa: F401
    TOP_RANKING_CATEGORIES,
    TOP_RANKING_CATEGORY_LABELS,
    TOP_RANKING_TOP_N,
    TopRankingCategorySpec,
    compute_top_ranking_candidate,
)
