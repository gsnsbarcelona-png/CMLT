# Tweet Automation

Aplicación web local para generar tweets a partir de datos reales de la LES/LEC (o por plantilla, o manualmente), revisarlos, copiarlos y opcionalmente publicarlos en X (Twitter) con un click.

En Compose hay seis modos visibles por defecto — **Calendario**, **Stats**, **H2H Hoy**, **Duelo 1v1**, **Efeméride** y **Cruce LEC** — más **Plantilla** y **Manual** disponibles en el código pero ocultos del selector (reactivarlos es agregar su `<label>` en `static/index.html`). Los modos de datos reales arman el texto con frases fijas a partir de los datos reales; la app no usa IA.

- **Calendario**: próximos partidos de **LES** y/o **LEC**, datos reales de la API pública de LoL Esports.
- **Stats**: "stats curiosas" (KDA, winrate, first blood, rivalidad/head-to-head entre equipos, y rango en ranked SoloQ vía lolpros.gg) con datos reales de **gol.gg** y **lolpros.gg**. **Split actual** o **Todo el año** (todos los torneos del año combinados), foco en un equipo/jugador, o rivalidad de un par puntual.
- **H2H Hoy**: preview del partido de LES de hoy (autodetectado) — historial directo, forma reciente de cada equipo, 2 variantes (historial / forma reciente).
- **Duelo 1v1**: para el partido de hoy/mañana (autodetectado), compara el KDA de temporada del jugador con más partidos en cada carril compartido por ambos equipos (roster y rol vía lolesports.com, stats vía gol.gg) — una tarjeta por carril con datos, ninguna si no hay suficiente info (no inventa alineaciones ni cruces históricos entre esos jugadores, esos datos no están disponibles).
- **Efeméride**: "un día como hoy" de la historia de la LES/Superliga, con una base curada de hitos verificados (no es scraping en vivo — ver limitaciones). 2 versiones: completa y "dato rápido".
- **Cruce LEC**: conecta la LES con la LEC — comparativa de rendimiento en vivo (gol.gg de ambas ligas) o jugadores que pasaron por las dos ligas (base curada). 2 tonos: dato sorprendente y pregunta a debate.

Cada resultado (y cada borrador/tweet del historial) tiene un botón **Copiar** para pegarlo directamente donde publiques manualmente, sin depender de la API de X. Calendario/Stats/Plantilla/Manual usan el editor compartido de abajo, con **Guardar borrador**/**Publicar ahora**; los modos que muestran varias variantes en tarjetas (H2H Hoy, Duelo 1v1, Efeméride, Cruce LEC) tienen un botón **Guardar** por tarjeta — nada se guarda solo, elegís qué variante(s) quedan como borrador.

## Requisitos previos

- Python 3.11 o superior.
- Una cuenta de X (Twitter) y acceso a [developer.x.com](https://developer.x.com).

## Instalación

Desde PowerShell, en la carpeta del proyecto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Después completá `.env` con tus credenciales (ver abajo).

## Conseguir las credenciales de X (Twitter)

Este es el paso más delicado, seguilo en orden:

1. Andá a [developer.x.com](https://developer.x.com) y aplicá para una cuenta de developer (el plan **Free** alcanza, incluye ~500 posts/mes).
2. Creá un **Project** y una **App** dentro del portal.
3. En la configuración de la App → **"User authentication settings"** → habilitá OAuth 1.0a, tipo de app "Web App" (o similar). Elegí permisos **"Read and Write"** (por defecto viene en solo lectura). Vas a tener que completar un Callback URL (podés poner `http://localhost:8000/callback`, no se usa realmente) y una Website URL (puede ser cualquiera, ej. tu perfil de X).
4. En la sección **"Keys and tokens"** de la App, copiá:
   - **API Key** y **API Key Secret** → van en `X_API_KEY` / `X_API_SECRET`.
5. En la misma pantalla, generá (botón **"Generate"**) el **Access Token and Secret**.
   > Importante: si ya los habías generado *antes* de configurar los permisos "Read and Write", **regeneralos** — si no, la publicación va a fallar con error 403.
6. Copiá esos valores en `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`.

## Calendario LES/LEC

No requiere configuración: `LOLESPORTS_API_KEY` en `.env.example` ya trae un valor funcional (la key pública que usa el propio sitio lolesports.com). Solo tendrías que tocarla si Riot la rota en el futuro y el modo Calendario empieza a fallar con error 502.

## Stats (gol.gg)

Tampoco requiere key (gol.gg es scraping de HTML público), pero **sí requiere mantenimiento manual en cada split nuevo**: los nombres de torneo cambian y hay que actualizarlos en `.env`.

- `GOLGG_TOURNAMENT`: el split actual (ej. `LES 2026 Summer`), usado cuando el scope es "Split actual".
- `GOLGG_YEAR_TOURNAMENTS`: lista separada por comas de todos los torneos del año (Kick-off + Spring + Spring Playoffs + Summer + Summer Playoffs), usada para el scope "Todo el año" y siempre para la rivalidad/head-to-head.
- `LEC_TOURNAMENT`: torneo de LEC usado en "Cruce LEC" (ej. `LEC 2026 Summer Season` — ojo que en gol.gg el nombre de la LEC lleva "Season" al final, a diferencia de LES).
- `GOLGG_SEASON`: el código de temporada de gol.gg (ej. `S16`), generalmente se mantiene igual todo el año calendario.

**Para encontrar el nombre exacto de un torneo nuevo** (ej. al arrancar un split), no hace falta buscar a mano en la web: la app expone `GET /api/generate/stats/available-tournaments` (parámetros opcionales `season` y `region`, por defecto la temporada configurada y `ES`), que pega directo al endpoint real que usa `gol.gg/tournament/list/` y devuelve el nombre exacto (`trname`), cantidad de partidos y rango de fechas de cada torneo. Con el server corriendo: `curl http://localhost:8000/api/generate/stats/available-tournaments`.

### Ranked SoloQ (lolpros.gg)

La categoría **Ranked (SoloQ)** de Stats no usa gol.gg sino [lolpros.gg](https://lolpros.gg): consulta en vivo el rango actual y el pico histórico de cada jugador de la LES (tier, LP, W/L). No requiere key ni configuración.

- **Solo consulta en vivo al generar el tweet** — la app no guarda historial de rangos ni corre nada en segundo plano (coherente con que no hay scheduler/cron), así que dos generaciones separadas por horas pueden reflejar rangos distintos, eso es lo esperado.
- El listado de jugadores sale directo del roster actual de gol.gg (`fetch_player_stats`), no hay una lista curada a mano.
- El slug de lolpros.gg se deriva automáticamente como el nombre de gol.gg en minúsculas (`https://lolpros.gg/player/{slug}`). Si algún jugador puntual no resuelve (nombre distinto entre ambos sitios, cuenta no encontrada), se omite en silencio de esa generación — no rompe el tweet, simplemente no aparece como candidato esa vez.
- Se evaluó `op.gg` como fuente alternativa pero se descartó: sus páginas de invocador no exponen un bloque de datos explotable sin ejecutar JS (a diferencia de lolpros.gg, que es server-rendered).
- Mismo cacheo en memoria de 5 minutos que gol.gg (ver más abajo), para no repetir ~30 pedidos si se genera varias veces seguidas.

### Arrobas y hashtags

`LEAGUE_HANDLE_LES`, `LEAGUE_HANDLE_LEC`, `CUSTOM_HASHTAGS` y `TEAM_HANDLES` en `.env` controlan qué se agrega al final de cada tweet generado. `TEAM_HANDLES` es una lista `Nombre de equipo:@handle` separada por comas, cargada a mano — la app nunca adivina un handle de equipo, así que si agregás una liga/torneo con equipos nuevos hay que sumarlos ahí. **Ojo**: `UB Alma Mater` queda **sin handle a propósito** — se probaron `@UniBarcelona` (cuenta general de la universidad) y `@EsportsUB` (que resultó ser el Servei d'Esports general de la UB, no el equipo de LoL) y ninguno de los dos es correcto. Agregalo si conseguís el handle real del equipo.

## Cruce LEC: base de jugadores

`app/data/les_lec_players.json` es una base curada (no scraping en vivo) de jugadores verificados que jugaron en LES/Superliga y en LEC. Para sumar uno nuevo, agregá una entrada con `player`, `fact` (el dato, con números/fechas concretas), `context` (matiz o dato secundario) y `source` (de dónde salió, no se muestra en el tweet) — verificando bien antes de cargarlo, la app no chequea esto por vos.

## Efeméride: base de hitos históricos

`app/data/les_anniversaries.json` es la misma idea que la anterior pero para "un día como hoy": una base curada de hitos de la historia de la LES/Superliga con fecha exacta (`month`, `day`, `year`, `headline`, `detail`, `era_name`, `teams`, `today_connection`, `source`). Liquipedia y Leaguepedia están protegidas con Cloudflare y no se pueden scrapear ni para investigar, así que expandir esta base es 100% manual: investigar con fuentes cruzadas y cargar a mano.

## Correr la app

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abrí [http://localhost:8000](http://localhost:8000) en el navegador.

Si te faltan credenciales, la app va a arrancar igual y te va a avisar con un cartel en la parte superior — podés seguir usando lo que sí esté configurado (por ejemplo, generar y copiar tweets sin credenciales de X).

## Estructura del proyecto

```
app/
  main.py, config.py, db.py, models.py
  data/         # les_anniversaries.json, les_lec_players.json (bases curadas)
  routers/      # tweets, generate, templates
  services/     # x_service, char_count,
                # lolesports_service (Calendario), golgg_service (Stats/H2H/Cruce LEC),
                # history_service (Efemeride), crossover_service (Cruce LEC: jugadores),
                # ranked_service (Stats: ranked SoloQ via lolpros.gg),
                # duel_service (Duelo 1v1: roster/rol de lolesports.com + stats de gol.gg)
static/         # frontend (HTML/CSS/JS, sin build step)
tests/          # pytest, con mocks para X, LoL Esports y gol.gg
```

## Correr los tests

```powershell
pytest
```

Los tests corren sin necesidad de credenciales reales (mockean las llamadas a X y a las fuentes de datos).

## Limitaciones conocidas

- El conteo de caracteres es una aproximación: las URLs se cuentan siempre como 23 caracteres (igual que el acortador t.co de X) y el resto se cuenta por code point Unicode. Puede diferir levemente del conteo real de X en casos extremos (emojis raros, texto CJK).
- No hay scheduler/calendario: la publicación es siempre manual e inmediata.
- Pensada para un solo usuario, corriendo en local.
- Stats "Todo el año" combina splits con **promedio ponderado por partidos jugados** — una aproximación razonable para stats curiosas, no matemáticamente exacta para ratios como K:D (no es lo mismo que recalcular desde los totales crudos de kills/deaths).
- gol.gg necesita mantenimiento manual cada split nuevo (ver sección Stats arriba, incluye cómo encontrar el nombre del torneo nuevo sin buscar a mano) — si Stats empieza a devolver "no hay datos" o 502, seguramente hay que actualizar `GOLGG_TOURNAMENT`/`GOLGG_YEAR_TOURNAMENTS`.
- Las respuestas de gol.gg y de lolpros.gg se cachean en memoria 5 minutos (por proceso, se pierde al reiniciar el server) para no repetir pedidos innecesarios — si el dato en vivo cambia, puede tardar hasta 5 minutos en reflejarse.
- Ranked (SoloQ) no guarda historial: cada generación consulta lolpros.gg en el momento, no hay tracking de evolución de rango a lo largo del tiempo (ver sección "Ranked SoloQ" arriba). Puede tardar hasta 20-30 segundos porque consulta ~30 páginas de lolpros.gg (en paralelo, pero es un sitio externo sin API).
- Efeméride y Cruce LEC (jugadores) usan bases curadas chicas, no scraping en vivo — la mayoría de los días no van a tener una efeméride exacta (muestra la más cercana y lo aclara) y la lista de cruces de jugadores es corta. Expandirlas es manual (ver secciones arriba).
- No hay handle verificado para UB Alma Mater (ver sección de arrobas arriba) — no se le arroba en los tweets hasta que se consiga el real.
- Duelo 1v1 depende de que lolesports.com tenga cargado el rol de cada jugador en `getTeams` — confirmado en vivo que algunos equipos lo tienen incompleto (la mayoría de los jugadores sin rol asignado), lo que da menos tarjetas de las esperadas para esos equipos. No hay forma de completarlo desde la app, es un dato de Riot. Tampoco confirma alineaciones oficiales del partido (Riot no las publica de antemano): si un equipo tiene más de un jugador en el mismo rol, se elige el que más partidos jugó esta temporada como proxy de titular.

## Troubleshooting

| Error al publicar | Causa probable |
|---|---|
| "credenciales... invalidas o expiraron" (401) | Keys de X mal copiadas o revocadas. |
| "permisos insuficientes" (403) | La app no tiene permisos "Read and Write", o el Access Token se generó antes de cambiarlos (hay que regenerarlo). |
| "muy similar a uno reciente" (403 duplicado) | X no permite publicar el mismo texto dos veces seguidas. Modificá el tweet. |
| "Limite de publicaciones alcanzado" (429) | Se llegó al límite del plan Free (~500 posts/mes). |
