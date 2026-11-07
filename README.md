# Tweet Automation

Aplicación web local para generar tweets a partir de datos reales de la LES/LEC (o por plantilla, o manualmente), revisarlos, copiarlos y opcionalmente publicarlos en X (Twitter) con un click.

En Compose hay siete modos visibles por defecto — **Calendario**, **Stats**, **H2H Hoy**, **Duelo 1v1**, **Top/Ranking**, **Efeméride** y **Cruce LEC** — más **Plantilla** y **Manual** disponibles en el código pero ocultos del selector (reactivarlos es agregar su `<label>` en `static/index.html`). Los modos de datos reales arman el texto con frases fijas a partir de los datos reales; la app no usa IA.

- **Calendario**: próximos partidos de **LES** y/o **LEC**, datos reales de la API pública de LoL Esports.
- **Stats**: "stats curiosas" (KDA, winrate, first blood, rivalidad/head-to-head entre equipos, y rango en ranked SoloQ vía lolpros.gg) con datos reales de **gol.gg** y **lolpros.gg**. **Split actual** o **Todo el año** (todos los torneos del año combinados), foco en un equipo/jugador, o rivalidad de un par puntual.
- **H2H Hoy**: preview del partido de LES de hoy (autodetectado) — historial directo, forma reciente de cada equipo, 2 variantes (historial / forma reciente). El selector de equipos incluye rivales de EMEA Masters (no solo LES), para cuando un equipo de LES se cruza ahí con alguien que nunca jugó en LES.
- **Duelo 1v1**: para el partido de hoy/mañana (autodetectado), compara el KDA de temporada del jugador con más partidos en cada carril compartido por ambos equipos (roster y rol vía lolesports.com, stats vía gol.gg) — una tarjeta por carril con datos, ninguna si no hay suficiente info (no inventa alineaciones ni cruces históricos entre esos jugadores, esos datos no están disponibles).
- **Top/Ranking**: top 3 real de una categoría de **gol.gg** para el split actual — KDA y farmeo (CS/min) por jugador; dragones/partida, torres/partida, primera sangre % y duración media (equipos que más rápido cierran) por equipo. Si hay menos de 3 con datos suficientes lo dice en vez de inventar posiciones. 2 variantes: foco en el líder y top 3 resumido. No incluye "partidas más rápidas" individuales (gol.gg no lo expone en listado, requeriría visitar cada partida una por una) ni el líder del split anterior como dato de contraste (la app no guarda histórico entre splits) — solo la media del split actual.
- **Efeméride**: "un día como hoy" de la historia de la LES/Superliga, con una base curada de hitos verificados (no es scraping en vivo — ver limitaciones). 2 versiones: completa y "dato rápido".
- **Cruce LEC**: conecta la LES con la LEC — comparativa de rendimiento en vivo (gol.gg de ambas ligas) o jugadores que pasaron por las dos ligas (base curada). 2 tonos: dato sorprendente y pregunta a debate.

Cada resultado (y cada borrador/tweet del historial) tiene un botón **Copiar** para pegarlo directamente donde publiques manualmente, sin depender de la API de X. Calendario/Stats/Plantilla/Manual usan el editor compartido de abajo, con **Guardar borrador**/**Publicar ahora**; los modos que muestran varias variantes en tarjetas (H2H Hoy, Duelo 1v1, Efeméride, Cruce LEC) tienen un botón **Guardar** por tarjeta — nada se guarda solo, elegís qué variante(s) quedan como borrador.

### Imagen adjunta (opcional)

Cualquier tweet (el del editor compartido, cada tarjeta de los modos múltiples, o un borrador ya guardado en la pestaña Borradores) puede llevar una imagen adjunta al publicarse en X. Formas de elegirla:

- **Automática**: cuando el resultado tiene un equipo de LES como protagonista claro (ej. Stats de un equipo puntual, H2H, Duelo, Top/Ranking de categoría de equipo, Efeméride con equipos, Cruce LEC de un equipo), aparece un botón "🛡️ Nombre del equipo" que trae su escudo directo de la API de LoL Esports (`getTeams`, campo `image`) — no hay imágenes curadas a mano, ni en categorías de jugador (gol.gg no da el equipo de cada jugador, no se inventa).
- **Fusión de escudos ("VS")**: cuando hay exactamente 2 equipos sugeridos (H2H, Duelo), aparece además "⚔️ Fusionar escudos" — arma un composite con los dos escudos lado a lado y un círculo "VS" en el medio (Pillow, server-side). Si no se encuentra el escudo de alguno de los dos, el botón directamente no aparece en vez de armar un composite a medias.
- **Fondo de marca**: el botón "🎨 Fondo del programa" (siempre disponible, no depende de equipos) arma un composite con el fondo del programa (`app/data/branding/background.png`) y el logo (`app/data/branding/logo.png`, PNG con fondo transparente) pegado del lado derecho (Pillow, server-side, ver `image_service.compose_branded_image`). Para cambiar el fondo o el logo, reemplazá esos dos archivos (mismos nombres) — no hace falta tocar código.
- **Manual**: botón "🖼️ Imagen" para subir cualquier archivo (PNG/JPG/GIF/WEBP, máx. 5 MB) — reemplaza a la sugerencia automática si había una.

La subida de medios a X sigue el endpoint v1.1 (`media/upload`) aunque el tweet se publique con la API v2 — usa las mismas 4 credenciales de X ya configuradas, sin permisos extra.

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

## Calendario LES/LEC/EMEA Masters

No requiere configuración: `LOLESPORTS_API_KEY` en `.env.example` ya trae un valor funcional (la key pública que usa el propio sitio lolesports.com). Solo tendrías que tocarla si Riot la rota en el futuro y el modo Calendario empieza a fallar con error 502.

Además de LES y LEC, el Calendario tiene una tercera liga: **EMEA Masters** (torneo semi-profesional que reúne a los mejores equipos de las ligas regionales europeas, incluida la LES — ej. el clasificatorio de Movistar KOI Fénix a EMEA Masters Summer 2026, que a su vez es la vía de la región EMEA para clasificar al WSCI). Mismo mecanismo que LES/LEC: `LEAGUE_HANDLE_EMEA_MASTERS` en `.env` controla la arroba de cierre (default `@EMEAmasters`, la cuenta oficial). Si Riot lanza otra liga/torneo nuevo y querés sumarlo, hay que resolver su `leagueId` a mano contra `GET /persisted/gw/getLeagues` (mismo endpoint, ver comentario en `lolesports_service.py`) y agregarlo a `LEAGUE_IDS`/`LEAGUE_LABELS`/`LEAGUE_HASHTAGS`/`LEAGUE_ORDER`/`LEAGUE_HANDLE_SETTINGS`.

## Stats (gol.gg)

Tampoco requiere key (gol.gg es scraping de HTML público), pero **sí requiere mantenimiento manual en cada split nuevo**: los nombres de torneo cambian y hay que actualizarlos en `.env`.

- `GOLGG_TOURNAMENT`: el split actual (ej. `LES 2026 Summer`), usado cuando el scope es "Split actual".
- `GOLGG_YEAR_TOURNAMENTS`: lista separada por comas de todos los torneos del año (Kick-off + Spring + Spring Playoffs + Summer + Summer Playoffs), usada para el scope "Todo el año" y siempre para la rivalidad/head-to-head.
- `LEC_TOURNAMENT`: torneo de LEC usado en "Cruce LEC" (ej. `LEC 2026 Summer Season` — ojo que en gol.gg el nombre de la LEC lleva "Season" al final, a diferencia de LES).
- `EMEA_MASTERS_TOURNAMENTS`: lista separada por comas de los torneos de EMEA Masters en gol.gg (región `WR` ahí, no `ES`). H2H la combina con `GOLGG_YEAR_TOURNAMENTS` — un equipo de LES que juega EMEA Masters se cruza con rivales que nunca jugaron en LES, y sin esto el historial/forma reciente de ese cruce sale siempre vacío.
- `GOLGG_SEASON`: el código de temporada de gol.gg (ej. `S16`), generalmente se mantiene igual todo el año calendario.

**Para encontrar el nombre exacto de un torneo nuevo** (ej. al arrancar un split), no hace falta buscar a mano en la web: la app expone `GET /api/generate/stats/available-tournaments` (parámetros opcionales `season` y `region`, por defecto la temporada configurada y `ES` — pasar `region=WR` para EMEA Masters, o `region=` vacío/omitido en la URL para buscar en todas las regiones), que pega directo al endpoint real que usa `gol.gg/tournament/list/` y devuelve el nombre exacto (`trname`), cantidad de partidos y rango de fechas de cada torneo. Con el server corriendo: `curl http://localhost:8000/api/generate/stats/available-tournaments`.

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

## Usarla desde el móvil (PWA / APK)

La app es instalable como PWA: desde Chrome en Android, abrís la URL y elegís **"Instalar app"** (o "Agregar a pantalla principal"). Queda con ícono propio y abre a pantalla completa. La interfaz se adapta a pantallas chicas. Toda la lógica (gol.gg, lolesports, lolpros.gg, publicación en X) sigue corriendo en el servidor, así que el móvil necesita llegar a un servidor donde corra la app.

**Opción rápida, en casa:** corré la app en tu PC con `--host 0.0.0.0` y abrí `http://IP-de-tu-PC:8000` desde el móvil en la misma Wi-Fi. Ojo: sin HTTPS Chrome no ofrece instalarla como app, pero se puede usar desde el navegador.

**Opción completa, desde cualquier lado:** subí la app a un servidor con HTTPS (Render, Fly.io, un VPS...). En ese caso:

1. **Activá el login, es obligatorio.** Cargá `APP_PASSWORD` (la contraseña para entrar) y `SESSION_SECRET` (generalo con `python -c "import secrets; print(secrets.token_hex(32))"`). Sin `APP_PASSWORD` cualquiera que encuentre la URL podría publicar en tu cuenta de X.
2. Arrancá uvicorn detrás del proxy HTTPS con `--proxy-headers --forwarded-allow-ips="*"`, para que la cookie de sesión se marque como `Secure`:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
   ```
3. La base SQLite tiene que estar en un disco persistente (`DATABASE_URL`), si no se pierden borradores e historial en cada deploy.
4. Cargá también en el servidor las credenciales de X y la config de gol.gg que tenías en `.env`.

**Render:** el repo incluye `render.yaml` (Blueprint). En render.com: New → Blueprint → elegí este repo, y cargá `APP_PASSWORD` y las 4 claves de X cuando lo pida. `SESSION_SECRET` se genera solo. Ojo: el plan gratuito tiene disco efímero (se pierden borradores e historial en cada deploy/reinicio) y duerme tras ~15 min sin uso; para persistir la base hace falta un disco de pago.

**APK:** con la PWA ya publicada en HTTPS, [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap) (`npx @bubblewrap/cli init --manifest https://TU-DOMINIO/static/manifest.webmanifest` y después `build`) genera un `.apk` que abre la app a pantalla completa. Para que no muestre la barra de URL hay que guardar el `assetlinks.json` que te genera Bubblewrap en `static/well-known/assetlinks.json`; la app lo sirve en `/.well-known/assetlinks.json`, y esa ruta queda abierta aunque el login esté activo.

Con `APP_PASSWORD` vacía (el valor por defecto) no se pide login, y la app funciona en local igual que siempre.

## Estructura del proyecto

```
app/
  main.py, config.py, db.py, models.py, auth.py (login opcional)
  data/         # les_anniversaries.json, les_lec_players.json (bases curadas)
  routers/      # tweets, templates, images (subida de imagenes)
                # generate/ (paquete, un sub-router por dominio: calendar, stats, duel,
                #            anniversary, league_comparison, top_ranking, template)
  services/     # x_service, char_count,
                # lolesports_service (Calendario), golgg_service (Stats/H2H/Cruce LEC),
                # history_service (Efemeride), crossover_service (Cruce LEC: jugadores),
                # ranked_service (Stats: ranked SoloQ via lolpros.gg),
                # duel_service (Duelo 1v1: roster/rol de lolesports.com + stats de gol.gg),
                # image_service (composite "VS" de dos escudos y fondo de marca, con Pillow)
static/         # frontend (HTML/CSS/JS, sin build step) + PWA (manifest, sw.js, icons/)
tests/          # pytest, con mocks para X, LoL Esports y gol.gg

data/             # gitignored -- generado en runtime
  tweets.db       # SQLite (borradores, historial)
  images/         # imagenes subidas a mano o descargadas para adjuntar a un tweet
```

## Correr los tests

```powershell
pytest
```

Los tests corren sin necesidad de credenciales reales (mockean las llamadas a X y a las fuentes de datos).

## Limitaciones conocidas

- El conteo de caracteres es una aproximación: las URLs se cuentan siempre como 23 caracteres (igual que el acortador t.co de X) y el resto se cuenta por code point Unicode. Puede diferir levemente del conteo real de X en casos extremos (emojis raros, texto CJK).
- No hay scheduler/calendario: la publicación es siempre manual e inmediata.
- Pensada para un solo usuario: el login es una única contraseña (`APP_PASSWORD`), no hay cuentas.
- Stats "Todo el año" combina splits con **promedio ponderado por partidos jugados** — una aproximación razonable para stats curiosas, no matemáticamente exacta para ratios como K:D (no es lo mismo que recalcular desde los totales crudos de kills/deaths).
- gol.gg necesita mantenimiento manual cada split nuevo (ver sección Stats arriba, incluye cómo encontrar el nombre del torneo nuevo sin buscar a mano) — si Stats empieza a devolver "no hay datos" o 502, seguramente hay que actualizar `GOLGG_TOURNAMENT`/`GOLGG_YEAR_TOURNAMENTS`.
- Las respuestas de gol.gg y de lolpros.gg se cachean en memoria 5 minutos (por proceso, se pierde al reiniciar el server) para no repetir pedidos innecesarios — si el dato en vivo cambia, puede tardar hasta 5 minutos en reflejarse.
- Ranked (SoloQ) no guarda historial: cada generación consulta lolpros.gg en el momento, no hay tracking de evolución de rango a lo largo del tiempo (ver sección "Ranked SoloQ" arriba). Puede tardar hasta 20-30 segundos porque consulta ~30 páginas de lolpros.gg (en paralelo, pero es un sitio externo sin API).
- Efeméride y Cruce LEC (jugadores) usan bases curadas chicas, no scraping en vivo — la mayoría de los días no van a tener una efeméride exacta (muestra la más cercana y lo aclara) y la lista de cruces de jugadores es corta. Expandirlas es manual (ver secciones arriba).
- No hay handle verificado para UB Alma Mater (ver sección de arrobas arriba) — no se le arroba en los tweets hasta que se consiga el real.
- Duelo 1v1 depende de que lolesports.com tenga cargado el rol de cada jugador en `getTeams` — confirmado en vivo que algunos equipos lo tienen incompleto (la mayoría de los jugadores sin rol asignado), lo que da menos tarjetas de las esperadas para esos equipos. No hay forma de completarlo desde la app, es un dato de Riot. Tampoco confirma alineaciones oficiales del partido (Riot no las publica de antemano): si un equipo tiene más de un jugador en el mismo rol, se elige el que más partidos jugó esta temporada como proxy de titular.
- Top/Ranking en categorías de jugador no muestra el equipo de cada jugador — la tabla de jugadores de gol.gg no expone esa columna, no se cruza con otra fuente para no arriesgar un match incorrecto. El dato de contraste es siempre la media del split actual; no hay forma de comparar contra el líder del split anterior porque la app no guarda histórico de stats entre splits.
- No hay Alembic ni otro sistema de migraciones: `init_db()` solo crea tablas nuevas y aplica un `ALTER TABLE` idempotente para las pocas columnas que se fueron agregando después (ver `_add_column_if_missing` en `db.py`) — sirve para este proyecto chico, pero un cambio de esquema más grande necesitaría hacerse a mano.
- La imagen adjunta a un tweet no se valida contra los requisitos de X (dimensiones, relación de aspecto) — si X la rechaza, se muestra el error tal cual lo devuelve la API en vez de anticiparlo del lado de la app.

## Troubleshooting

| Error al publicar | Causa probable |
|---|---|
| "credenciales... invalidas o expiraron" (401) | Keys de X mal copiadas o revocadas. |
| "permisos insuficientes" (403) | La app no tiene permisos "Read and Write", o el Access Token se generó antes de cambiarlos (hay que regenerarlo). |
| "muy similar a uno reciente" (403 duplicado) | X no permite publicar el mismo texto dos veces seguidas. Modificá el tweet. |
| "Limite de publicaciones alcanzado" (429) | Se llegó al límite del plan Free (~500 posts/mes). |
