const TWEET_CHAR_LIMIT = 280;
const URL_PLACEHOLDER_LEN = 23;
const URL_PATTERN = /https?:\/\/\S+/g;

function countChars(text) {
  const urls = text.match(URL_PATTERN) || [];
  const withoutUrls = text.replace(URL_PATTERN, "");
  return Array.from(withoutUrls).length + urls.length * URL_PLACEHOLDER_LEN;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const isJson = res.status !== 204 && res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : null;
  if (res.status === 401) {
    // Sesion expirada (solo pasa con APP_PASSWORD configurada).
    window.location.replace("/login");
    throw new Error("Sesion expirada.");
  }
  if (!res.ok) {
    const message = body?.detail || `Error ${res.status}`;
    throw new Error(message);
  }
  return body;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    // Fallback para navegadores/contextos sin permiso de Clipboard API
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e2) {
      ok = false;
    }
    document.body.removeChild(textarea);
    return ok;
  }
}

function flashButtonLabel(button, tempLabel) {
  const original = button.textContent;
  button.textContent = tempLabel;
  button.disabled = true;
  setTimeout(() => {
    button.textContent = original;
    button.disabled = false;
  }, 1200);
}

function bindCopyButton(button, getText) {
  button.addEventListener("click", async () => {
    const ok = await copyToClipboard(getText());
    flashButtonLabel(button, ok ? "Copiado!" : "No se pudo copiar");
  });
}

// Boton "Abrir en X": abre el compositor de X (web intent) con el texto ya
// escrito, en la cuenta que este activa en ese navegador/app -- no usa la API
// ni las credenciales del servidor. Limitacion: el intent no admite imagenes.
function bindOpenXButton(button, getText) {
  button.addEventListener("click", () => {
    const text = getText();
    if (!text || !text.trim()) return;
    window.open(`https://x.com/intent/post?text=${encodeURIComponent(text)}`, "_blank", "noopener");
  });
}

// Boton "Guardar" de las tarjetas de resultado (H2H, Efemeride, Cruce LEC,
// Lote): ninguno de esos modos auto-guarda -- el usuario elige que
// variante(s) quedan como borrador, con el mismo endpoint que usa el
// "Guardar borrador" del compose compartido.
function bindSaveButton(button, getText, source, getImageUrl) {
  button.addEventListener("click", async () => {
    try {
      const payload = { content: getText(), source, image_url: getImageUrl ? getImageUrl() || null : null };
      await api("/api/tweets", { method: "POST", body: JSON.stringify(payload) });
      flashButtonLabel(button, "Guardado!");
    } catch (e) {
      alert(e.message);
    }
  });
}

// Imagen opcional adjunta a un tweet: mismo bloque HTML e igual logica de
// binding en el editor compartido de Compose, en cada tarjeta de resultado
// (H2H, Duelo, Top/Ranking, Efemeride, Cruce LEC, Lote) y en cada borrador de
// la pestana Borradores. El estado (image_url actual, o "" si no hay) vive en
// `root.dataset.imageUrl` -- quien maneje Guardar/Publicar para ese `root` lo
// lee de ahi en el momento de guardar, no hace falta pasarlo por argumentos.
function imagePickerHtml() {
  return `
    <div class="image-picker">
      <div class="image-suggestions"></div>
      <div class="image-branding"><button type="button" class="use-branded-bg-btn">🎨 Fondo del programa</button></div>
      <label class="image-upload-label">🖼️ Imagen<input type="file" accept="image/*" class="image-upload-input" /></label>
      <img class="image-preview" hidden />
      <button type="button" class="remove-image-btn" hidden>Quitar imagen</button>
    </div>
  `;
}

function bindImagePicker(root, { suggestedTeams = [], initialUrl = null } = {}) {
  const suggestionsEl = root.querySelector(".image-suggestions");
  const fileInput = root.querySelector(".image-upload-input");
  const preview = root.querySelector(".image-preview");
  const removeBtn = root.querySelector(".remove-image-btn");
  if (!fileInput) return; // este root no tiene selector de imagen (ej. tarjeta de error)

  function setImage(url) {
    root.dataset.imageUrl = url || "";
    preview.src = url || "";
    preview.hidden = !url;
    removeBtn.hidden = !url;
  }

  if (suggestedTeams.length) {
    const vsButton =
      suggestedTeams.length === 2 ? `<button type="button" class="use-vs-logo-btn">⚔️ Fusionar escudos</button>` : "";
    suggestionsEl.innerHTML =
      suggestedTeams.map((t) => `<button type="button" class="use-logo-btn">🛡️ ${escapeHtml(t)}</button>`).join("") +
      vsButton;
    suggestionsEl.querySelectorAll(".use-logo-btn").forEach((btn, idx) => {
      const team = suggestedTeams[idx];
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          const res = await api(`/api/generate/team-logo?team=${encodeURIComponent(team)}`);
          if (res.image_url) {
            setImage(res.image_url);
          } else {
            alert(`No encontramos el escudo de ${team}.`);
          }
        } catch (e) {
          alert(e.message);
        } finally {
          btn.disabled = false;
        }
      });
    });
    const vsBtn = suggestionsEl.querySelector(".use-vs-logo-btn");
    if (vsBtn) {
      vsBtn.addEventListener("click", async () => {
        vsBtn.disabled = true;
        try {
          const params = new URLSearchParams({ team_a: suggestedTeams[0], team_b: suggestedTeams[1] });
          const res = await api(`/api/generate/team-vs-logo?${params}`);
          setImage(res.image_url);
        } catch (e) {
          alert(e.message);
        } finally {
          vsBtn.disabled = false;
        }
      });
    }
  }

  const brandedBtn = root.querySelector(".use-branded-bg-btn");
  brandedBtn.addEventListener("click", async () => {
    brandedBtn.disabled = true;
    try {
      const params = new URLSearchParams();
      if (suggestedTeams[0]) params.set("team_a", suggestedTeams[0]);
      if (suggestedTeams[1]) params.set("team_b", suggestedTeams[1]);
      const query = params.toString();
      const res = await api(`/api/generate/branded-image${query ? `?${query}` : ""}`);
      setImage(res.image_url);
    } catch (e) {
      alert(e.message);
    } finally {
      brandedBtn.disabled = false;
    }
  });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/images", { method: "POST", body: formData });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `Error ${res.status}`);
      setImage(body.image_url);
    } catch (e) {
      alert(e.message);
    } finally {
      fileInput.value = "";
    }
  });

  removeBtn.addEventListener("click", () => setImage(null));

  setImage(initialUrl);
}

// Patron compartido por los modos de Compose que generan varias tarjetas de
// resultado a partir de UN pedido (H2H, Duelo 1v1, Top/Ranking, Efemeride,
// Cruce LEC, Lote): mismo esqueleto de tarjeta (meta + contenido + Guardar/
// Copiar), mismo manejo de boton/carga/error -- solo cambian el endpoint, el
// payload, el texto de "meta" de cada tarjeta (distinto dato por modo: angulo,
// rol, variante, tono, tema...) y el `source` usado para Guardar (que tambien
// nombra las clases CSS `save-${source}-btn`/`copy-${source}-btn` de cada
// modo, ya consistentes en el HTML). metaFn(result) da ese texto de meta.
function variantResultCardHtml(result, source, metaFn) {
  const meta = metaFn(result);
  if (result.error) {
    return `
      <div class="card">
        <div class="card-meta">${escapeHtml(meta)}</div>
        <div class="card-error">${escapeHtml(result.error)}</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-meta">${escapeHtml(meta)} · ${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      <div class="card-content">${escapeHtml(result.content)}</div>
      ${imagePickerHtml()}
      <div class="card-actions">
        <button class="save-${source}-btn">Guardar</button>
        <button class="copy-${source}-btn">Copiar</button>
        <button class="open-x-${source}-btn" title="Abre X con el texto listo (sin imagen)">Abrir en X</button>
      </div>
    </div>
  `;
}

async function generateResultCards({ endpoint, payload, resultsElId, btnId, source, metaFn, loadingText, emptyMessage }) {
  const resultsEl = document.getElementById(resultsElId);
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  resultsEl.innerHTML = loadingText;
  try {
    const results = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    if (!results.length && emptyMessage) {
      resultsEl.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
      return;
    }
    resultsEl.innerHTML = results.map((r) => variantResultCardHtml(r, source, metaFn)).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindImagePicker(card, { suggestedTeams: r.suggested_teams || [] });
        bindCopyButton(card.querySelector(`.copy-${source}-btn`), () => r.content);
        bindOpenXButton(card.querySelector(`.open-x-${source}-btn`), () => r.content);
        bindSaveButton(card.querySelector(`.save-${source}-btn`), () => r.content, source, () => card.dataset.imageUrl);
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

// ---------- Tabs ----------
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "drafts") loadDrafts();
  if (name === "history") loadHistory();
  if (name === "templates") loadTemplatesTab();
}

// ---------- Config banner ----------
async function checkConfig() {
  try {
    const cfg = await api("/api/config/check");
    const banner = document.getElementById("config-banner");
    const missing = [];
    if (!cfg.x_configured) missing.push("X (publicacion)");
    if (missing.length) {
      banner.textContent = `Falta configurar en .env: ${missing.join(", ")}.`;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch (e) {
    // silencioso: si /api/config/check falla, no bloqueamos la UI
  }
}

// ---------- Compose ----------
function initCompose() {
  const modeRadios = document.querySelectorAll('input[name="mode"]');
  modeRadios.forEach((r) => r.addEventListener("change", updateComposeMode));
  updateComposeMode();

  const contentEl = document.getElementById("compose-content");
  contentEl.addEventListener("input", updateCharCounter);
  updateCharCounter();

  document.getElementById("image-picker").innerHTML = imagePickerHtml();
  bindImagePicker(document.getElementById("image-picker"));
  document.getElementById("template-render-btn").addEventListener("click", handleTemplateRender);
  document.getElementById("save-draft-btn").addEventListener("click", () => handleSave(false));
  document.getElementById("publish-now-btn").addEventListener("click", () => handleSave(true));
  document.getElementById("calendar-generate-btn").addEventListener("click", handleCalendarGenerate);
  document.getElementById("stats-generate-btn").addEventListener("click", handleStatsGenerate);
  document.getElementById("h2h-autofill-btn").addEventListener("click", handleH2hAutofill);
  document.getElementById("h2h-generate-btn").addEventListener("click", handleH2hGenerate);
  document.getElementById("duel-autofill-btn").addEventListener("click", handleDuelAutofill);
  document.getElementById("duel-generate-btn").addEventListener("click", handleDuelGenerate);
  document.getElementById("top-ranking-generate-btn").addEventListener("click", handleTopRankingGenerate);
  document.getElementById("anniversary-generate-btn").addEventListener("click", handleAnniversaryGenerate);
  document.getElementById("lec-compare-generate-btn").addEventListener("click", handleLecCompareGenerate);
  bindCopyButton(document.getElementById("copy-content-btn"), () => document.getElementById("compose-content").value);
  bindOpenXButton(document.getElementById("open-x-btn"), () => document.getElementById("compose-content").value);

  loadTemplateSelect();
  loadTopRankingCategories();
  loadTeamOptions(["rivalry-team-a", "rivalry-team-b", "ranked-team-a", "ranked-team-b", "duel-team-a", "duel-team-b"]);
  // H2H usa una lista mas amplia que el resto de los modos: ademas de LES,
  // incluye los rivales de EMEA Masters (para poder armar H2H cuando un
  // equipo de LES juega ahi contra alguien que nunca jugo en LES).
  loadTeamOptions(["h2h-team-a", "h2h-team-b"], "/api/generate/stats/h2h-teams");
}

async function loadTeamOptions(selectIds, endpoint = "/api/generate/stats/teams") {
  try {
    const teams = await api(endpoint);
    const options = teams.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    selectIds.forEach((id) => document.getElementById(id).insertAdjacentHTML("beforeend", options));
  } catch (e) {
    // silencioso: si gol.gg no responde, el usuario todavia puede usar el resto de la app
  }
}

// lolesports.com y gol.gg no siempre usan el mismo nombre de equipo (ej.
// "UCAM Esports Club" vs "UCAM Esports", "Barça Esports" vs "Barca eSports"
// con tilde) -- mismo criterio que ya usa el backend (normalize_team_name):
// sacar acentos, pasar a minuscula, y matchear por substring en vez de
// igualdad exacta.
// Rango Unicode de marcas diacriticas combinantes (U+0300-U+036F) construido
// por codigo (String.fromCharCode) en vez de caracteres literales en el
// fuente -- evita cualquier ambiguedad de codificacion/visualizacion del
// archivo con caracteres combinantes sueltos (que no tienen una letra base
// antes en la clase de regex, se renderizan raro en editores/terminales).
const COMBINING_DIACRITICS_PATTERN = new RegExp(
  "[" + String.fromCharCode(0x300) + "-" + String.fromCharCode(0x36f) + "]",
  "g"
);

function normalizeTeamName(name) {
  return name.normalize("NFKD").replace(COMBINING_DIACRITICS_PATTERN, "").toLowerCase();
}

function selectTeamOption(selectEl, rawName) {
  const wanted = normalizeTeamName(rawName);
  const match = Array.from(selectEl.options).find((o) => {
    if (!o.value) return false;
    const norm = normalizeTeamName(o.value);
    return norm === wanted || norm.includes(wanted) || wanted.includes(norm);
  });
  if (match) selectEl.value = match.value;
  return !!match;
}

function updateComposeMode() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  document.getElementById("mode-calendar").hidden = mode !== "calendar";
  document.getElementById("mode-stats").hidden = mode !== "stats";
  document.getElementById("mode-h2h").hidden = mode !== "h2h";
  document.getElementById("mode-duel").hidden = mode !== "duel";
  document.getElementById("mode-top-ranking").hidden = mode !== "top-ranking";
  document.getElementById("mode-anniversary").hidden = mode !== "anniversary";
  document.getElementById("mode-lec-compare").hidden = mode !== "lec-compare";
  document.getElementById("mode-template").hidden = mode !== "template";
  document.getElementById("mode-manual").hidden = mode !== "manual";
  document.getElementById("single-compose-area").hidden =
    mode === "h2h" ||
    mode === "duel" ||
    mode === "top-ranking" ||
    mode === "anniversary" ||
    mode === "lec-compare";
}

async function loadTopRankingCategories() {
  const select = document.getElementById("top-ranking-category");
  try {
    const categories = await api("/api/generate/top-ranking/categories");
    select.innerHTML = Object.entries(categories)
      .map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`)
      .join("");
  } catch (e) {
    // silencioso: si falla, el select queda vacio pero el resto de la app sigue andando
  }
}

async function handleLecCompareGenerate() {
  const focus = document.getElementById("lec-compare-focus").value.trim();

  await generateResultCards({
    endpoint: "/api/generate/league-comparison",
    payload: { focus: focus || null },
    resultsElId: "lec-compare-results",
    btnId: "lec-compare-generate-btn",
    source: "lec-compare",
    metaFn: (r) => (r.tone === "debate" ? "Tono: pregunta a debate" : "Tono: dato sorprendente"),
    loadingText: "Consultando gol.gg (LES y LEC)...",
  });
}

async function handleAnniversaryGenerate() {
  await generateResultCards({
    endpoint: "/api/generate/anniversary",
    payload: {},
    resultsElId: "anniversary-results",
    btnId: "anniversary-generate-btn",
    source: "anniversary",
    metaFn: (r) => {
      const formatLabel = r.format === "completo" ? "Version completa" : "Dato rapido";
      const exactNote = r.is_exact ? "" : " (no es de hoy exacto, ver texto)";
      return `${formatLabel}${exactNote}`;
    },
    loadingText: "Buscando efemeride...",
  });
}

// Patron compartido por los botones "Autocompletar" de H2H y Duelo: pedir
// el partido de hoy/manana al endpoint indicado, completar los dos <select>
// de equipos (via selectTeamOption, porque lolesports.com y gol.gg no
// siempre usan el mismo nombre) y mostrar feedback de que paso. Solo cambian
// los IDs de los elementos, el endpoint y los mensajes cuando no hay partido
// o hay varios.
async function runTeamAutofill({ feedbackId, teamAId, teamBId, endpoint, loadingMessage, noMatchMessage, multiMessagePrefix }) {
  const feedback = document.getElementById(feedbackId);
  feedback.textContent = loadingMessage;
  try {
    const matches = await api(endpoint);
    if (matches.length === 0) {
      feedback.textContent = noMatchMessage;
    } else if (matches.length === 1) {
      const okA = selectTeamOption(document.getElementById(teamAId), matches[0].team_a);
      const okB = selectTeamOption(document.getElementById(teamBId), matches[0].team_b);
      feedback.textContent =
        okA && okB
          ? `Completado: ${matches[0].team_a} vs ${matches[0].team_b} (${matches[0].block_name}).`
          : `No encontramos "${matches[0].team_a} vs ${matches[0].team_b}" en la lista de gol.gg -- elegi los equipos a mano.`;
    } else {
      const list = matches.map((m) => `${m.team_a} vs ${m.team_b}`).join(", ");
      feedback.textContent = `${multiMessagePrefix}, elegi los equipos a mano: ${list}.`;
    }
  } catch (e) {
    feedback.textContent = e.message;
  }
}

async function handleH2hAutofill() {
  await runTeamAutofill({
    feedbackId: "h2h-autofill-feedback",
    teamAId: "h2h-team-a",
    teamBId: "h2h-team-b",
    endpoint: "/api/generate/stats/today-match",
    loadingMessage: "Consultando calendario de hoy...",
    noMatchMessage: "No hay partido de LES programado para hoy.",
    multiMessagePrefix: "Hay varios partidos hoy",
  });
}

async function handleH2hGenerate() {
  const teamA = document.getElementById("h2h-team-a").value;
  const teamB = document.getElementById("h2h-team-b").value;
  if (!teamA || !teamB) {
    document.getElementById("h2h-results").innerHTML = '<div class="empty-state">Elegi los dos equipos.</div>';
    return;
  }

  await generateResultCards({
    endpoint: "/api/generate/stats/head-to-head-preview",
    payload: { team_a: teamA, team_b: teamB },
    resultsElId: "h2h-results",
    btnId: "h2h-generate-btn",
    source: "h2h",
    metaFn: (r) => (r.angle === "historial" ? "Enfoque: historial" : "Enfoque: forma reciente"),
    loadingText: "Generando...",
  });
}

async function handleDuelAutofill() {
  await runTeamAutofill({
    feedbackId: "duel-autofill-feedback",
    teamAId: "duel-team-a",
    teamBId: "duel-team-b",
    endpoint: "/api/generate/duel/today-match",
    loadingMessage: "Consultando calendario de hoy/mañana...",
    noMatchMessage: "No hay partido de LES programado para hoy ni mañana.",
    multiMessagePrefix: "Hay varios partidos",
  });
}

async function handleDuelGenerate() {
  const teamA = document.getElementById("duel-team-a").value;
  const teamB = document.getElementById("duel-team-b").value;
  if (!teamA || !teamB) {
    document.getElementById("duel-results").innerHTML = '<div class="empty-state">Elegi los dos equipos.</div>';
    return;
  }

  await generateResultCards({
    endpoint: "/api/generate/duel",
    payload: { team_a: teamA, team_b: teamB },
    resultsElId: "duel-results",
    btnId: "duel-generate-btn",
    source: "duel",
    metaFn: (r) => `${r.role} · ${r.subject}`,
    loadingText: "Generando...",
    emptyMessage: "No hay ningun carril con datos suficientes en ambos equipos para armar un duelo.",
  });
}

async function handleTopRankingGenerate() {
  const category = document.getElementById("top-ranking-category").value;
  if (!category) {
    document.getElementById("top-ranking-results").innerHTML = '<div class="empty-state">Elegi una categoria.</div>';
    return;
  }

  await generateResultCards({
    endpoint: "/api/generate/top-ranking",
    payload: { category },
    resultsElId: "top-ranking-results",
    btnId: "top-ranking-generate-btn",
    source: "top-ranking",
    metaFn: (r) => (r.variant === "top1" ? "Foco en el lider" : "Top 3 resumido"),
    loadingText: "Consultando gol.gg...",
  });
}

async function handleStatsGenerate() {
  const rivalryTeamA = document.getElementById("rivalry-team-a").value;
  const rivalryTeamB = document.getElementById("rivalry-team-b").value;
  const usingRivalry = rivalryTeamA && rivalryTeamB;

  const rankedPlayerA = document.getElementById("ranked-player-a").value.trim();
  const rankedPlayerB = document.getElementById("ranked-player-b").value.trim();
  const usingRankedPlayers = rankedPlayerA && rankedPlayerB;

  const rankedTeamA = document.getElementById("ranked-team-a").value;
  const rankedTeamB = document.getElementById("ranked-team-b").value;
  const usingRankedTeams = rankedTeamA && rankedTeamB;

  const categories = [];
  if (document.getElementById("stats-teams").checked) categories.push("teams");
  if (document.getElementById("stats-players").checked) categories.push("players");
  if (document.getElementById("stats-ranked").checked) categories.push("ranked");

  if (!usingRivalry && !usingRankedPlayers && !usingRankedTeams && !categories.length) {
    setComposeFeedback(
      "Marca al menos una categoria (equipos, jugadores o ranked), elegi los dos equipos de rivalidad, o elegi un par a comparar en elo.",
      true
    );
    return;
  }
  const focus = document.getElementById("stats-focus").value.trim();
  const scope = document.querySelector('input[name="stats-scope"]:checked').value;

  const usesLolpros = categories.includes("ranked") || usingRankedPlayers || usingRankedTeams;
  setComposeFeedback(
    usesLolpros ? "Consultando gol.gg y lolpros.gg (puede tardar unos segundos)..." : "Consultando gol.gg...",
    false
  );
  await fillComposeFromGenerate(
    "/api/generate/stats",
    {
      categories,
      focus: focus || null,
      scope,
      rivalry_team_a: rivalryTeamA || null,
      rivalry_team_b: rivalryTeamB || null,
      ranked_player_a: rankedPlayerA || null,
      ranked_player_b: rankedPlayerB || null,
      ranked_team_a: rankedTeamA || null,
      ranked_team_b: rankedTeamB || null,
    },
    "Stat generado. Podes editarlo antes de guardar o publicar."
  );
}

async function handleCalendarGenerate() {
  const leagues = [];
  if (document.getElementById("calendar-les").checked) leagues.push("les");
  if (document.getElementById("calendar-lec").checked) leagues.push("lec");
  if (document.getElementById("calendar-emea-masters").checked) leagues.push("emea_masters");

  if (!leagues.length) {
    setComposeFeedback("Marca al menos una liga (LES o LEC).", true);
    return;
  }
  setComposeFeedback("Consultando calendario...", false);
  await fillComposeFromGenerate(
    "/api/generate/calendar",
    { leagues },
    "Calendario generado. Podes editarlo antes de guardar o publicar."
  );
}

function updateCharCounter() {
  const text = document.getElementById("compose-content").value;
  const count = countChars(text);
  const counter = document.getElementById("compose-char-counter");
  counter.textContent = `${count} / ${TWEET_CHAR_LIMIT}`;
  counter.classList.remove("warn", "over");
  if (count > TWEET_CHAR_LIMIT) counter.classList.add("over");
  else if (count > 260) counter.classList.add("warn");
  document.getElementById("publish-now-btn").disabled = count > TWEET_CHAR_LIMIT || count === 0;
}

function setComposeFeedback(message, isError) {
  const el = document.getElementById("compose-feedback");
  el.textContent = message || "";
  el.classList.toggle("error", !!isError);
  el.classList.toggle("success", !isError && !!message);
}

// Patron compartido por los modos de Compose que generan texto y lo vuelcan
// en el editor (Calendario, Stats, Plantilla): pegarle al endpoint,
// llenar compose-content, y mostrar feedback de exito/error.
async function fillComposeFromGenerate(endpoint, payload, successMessage) {
  try {
    const result = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("compose-content").value = result.content;
    updateCharCounter();
    // Re-arma el selector de imagen con las sugerencias de esta generacion
    // (ej. el escudo del equipo, si el resultado es de un equipo puntual) --
    // no se pisa una imagen ya elegida a mano si esta generacion no sugiere nada.
    const imagePicker = document.getElementById("image-picker");
    if (result.suggested_teams && result.suggested_teams.length) {
      imagePicker.innerHTML = imagePickerHtml();
      bindImagePicker(imagePicker, { suggestedTeams: result.suggested_teams });
    }
    setComposeFeedback(successMessage, false);
  } catch (e) {
    setComposeFeedback(e.message, true);
  }
}

async function loadTemplateSelect() {
  const select = document.getElementById("template-select");
  try {
    const templates = await api("/api/templates");
    select.innerHTML = templates.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");
    select.dataset.templates = JSON.stringify(templates);
    select.onchange = renderTemplateVariableInputs;
    renderTemplateVariableInputs();
  } catch (e) {
    select.innerHTML = "<option>No se pudieron cargar las plantillas</option>";
  }
}

function renderTemplateVariableInputs() {
  const select = document.getElementById("template-select");
  const templates = JSON.parse(select.dataset.templates || "[]");
  const template = templates.find((t) => String(t.id) === select.value);
  const container = document.getElementById("template-variables");
  if (!template) {
    container.innerHTML = "";
    return;
  }
  const varNames = Array.from(new Set(Array.from(template.template_text.matchAll(/\{(\w+)\}/g)).map((m) => m[1])));
  container.innerHTML = varNames
    .map(
      (name) =>
        `<label class="var-input">${escapeHtml(name)}<input type="text" data-var="${escapeHtml(name)}" /></label>`
    )
    .join("");
}

async function handleTemplateRender() {
  const select = document.getElementById("template-select");
  if (!select.value) {
    setComposeFeedback("No hay plantillas disponibles. Crea una en la pestana Plantillas.", true);
    return;
  }
  const variables = {};
  document.querySelectorAll("#template-variables [data-var]").forEach((input) => {
    variables[input.dataset.var] = input.value;
  });
  await fillComposeFromGenerate(
    "/api/generate/template",
    { template_id: Number(select.value), variables },
    "Plantilla renderizada. Podes editarla antes de guardar o publicar."
  );
}

async function handleSave(publishNow) {
  const content = document.getElementById("compose-content").value.trim();
  if (!content) {
    setComposeFeedback("El contenido no puede estar vacio.", true);
    return;
  }
  if (countChars(content) > TWEET_CHAR_LIMIT) {
    setComposeFeedback(`El tweet supera el limite de ${TWEET_CHAR_LIMIT} caracteres.`, true);
    return;
  }
  const mode = document.querySelector('input[name="mode"]:checked').value;

  if (publishNow) {
    const confirmed = confirm("¿Publicar este tweet ahora en X? Esta accion es publica e irreversible.");
    if (!confirmed) return;
  }

  const imageUrl = document.getElementById("image-picker").dataset.imageUrl || null;

  try {
    const tweet = await api("/api/tweets", {
      method: "POST",
      body: JSON.stringify({ content, source: mode, image_url: imageUrl }),
    });

    if (!publishNow) {
      setComposeFeedback("Borrador guardado.", false);
      resetCompose();
      return;
    }

    const published = await api(`/api/tweets/${tweet.id}/publish`, { method: "POST" });
    if (published.status === "published") {
      setComposeFeedback(`Tweet publicado (id ${published.tweet_id}).`, false);
      resetCompose();
    } else {
      setComposeFeedback(`No se pudo publicar: ${published.error_message}`, true);
    }
  } catch (e) {
    setComposeFeedback(e.message, true);
  }
}

function resetCompose() {
  document.getElementById("compose-content").value = "";
  const imagePicker = document.getElementById("image-picker");
  imagePicker.innerHTML = imagePickerHtml();
  bindImagePicker(imagePicker);
  updateCharCounter();
}

// ---------- Drafts ----------
async function loadDrafts() {
  const container = document.getElementById("drafts-list");
  container.innerHTML = "Cargando...";
  try {
    const drafts = await api("/api/tweets?status=draft");
    if (!drafts.length) {
      container.innerHTML = '<div class="empty-state">No hay borradores. Creá uno en Compose.</div>';
      return;
    }
    container.innerHTML = drafts.map(draftCardHtml).join("");
    drafts.forEach((d) => bindDraftCard(d));
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Error cargando borradores: ${escapeHtml(e.message)}</div>`;
  }
}

function draftCardHtml(tweet) {
  return `
    <div class="card" data-id="${tweet.id}">
      <div class="card-header">
        <span class="badge badge-draft">Borrador</span>
        <span class="card-meta">${formatDate(tweet.created_at)} · ${escapeHtml(tweet.source)}</span>
      </div>
      <textarea class="card-edit" rows="3">${escapeHtml(tweet.content)}</textarea>
      <div class="char-counter draft-char-counter">0 / 280</div>
      ${imagePickerHtml()}
      <div class="card-actions">
        <button class="save-edit-btn">Guardar cambios</button>
        <button class="copy-draft-btn">Copiar</button>
        <button class="open-x-draft-btn" title="Abre X con el texto listo (sin imagen)">Abrir en X</button>
        <button class="publish-btn primary">Publicar ahora</button>
        <button class="delete-btn">Eliminar</button>
      </div>
      <div class="feedback card-feedback"></div>
    </div>
  `;
}

function bindDraftCard(tweet) {
  const card = document.querySelector(`#drafts-list .card[data-id="${tweet.id}"]`);
  const textarea = card.querySelector(".card-edit");
  const counter = card.querySelector(".draft-char-counter");
  const feedback = card.querySelector(".card-feedback");

  const updateCounter = () => {
    const count = countChars(textarea.value);
    counter.textContent = `${count} / ${TWEET_CHAR_LIMIT}`;
    counter.classList.remove("warn", "over");
    if (count > TWEET_CHAR_LIMIT) counter.classList.add("over");
    else if (count > 260) counter.classList.add("warn");
  };
  textarea.addEventListener("input", updateCounter);
  updateCounter();

  bindImagePicker(card, { initialUrl: tweet.image_url || null });
  bindCopyButton(card.querySelector(".copy-draft-btn"), () => textarea.value);
  bindOpenXButton(card.querySelector(".open-x-draft-btn"), () => textarea.value);

  card.querySelector(".save-edit-btn").addEventListener("click", async () => {
    try {
      await api(`/api/tweets/${tweet.id}`, {
        method: "PUT",
        body: JSON.stringify({ content: textarea.value, image_url: card.dataset.imageUrl || null }),
      });
      feedback.textContent = "Guardado.";
      feedback.classList.add("success");
    } catch (e) {
      feedback.textContent = e.message;
      feedback.classList.add("error");
    }
  });

  card.querySelector(".publish-btn").addEventListener("click", async () => {
    if (!confirm("¿Publicar este tweet ahora en X? Esta accion es publica e irreversible.")) return;
    try {
      await api(`/api/tweets/${tweet.id}`, {
        method: "PUT",
        body: JSON.stringify({ content: textarea.value, image_url: card.dataset.imageUrl || null }),
      });
      const published = await api(`/api/tweets/${tweet.id}/publish`, { method: "POST" });
      if (published.status === "published") {
        loadDrafts();
      } else {
        feedback.textContent = `No se pudo publicar: ${published.error_message}`;
        feedback.classList.add("error");
      }
    } catch (e) {
      feedback.textContent = e.message;
      feedback.classList.add("error");
    }
  });

  card.querySelector(".delete-btn").addEventListener("click", async () => {
    if (!confirm("¿Eliminar este borrador?")) return;
    try {
      await api(`/api/tweets/${tweet.id}`, { method: "DELETE" });
      loadDrafts();
    } catch (e) {
      feedback.textContent = e.message;
      feedback.classList.add("error");
    }
  });
}

// ---------- History ----------
async function loadHistory() {
  const container = document.getElementById("history-list");
  container.innerHTML = "Cargando...";
  try {
    const [published, failed] = await Promise.all([
      api("/api/tweets?status=published"),
      api("/api/tweets?status=failed"),
    ]);
    const items = [...published, ...failed].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    if (!items.length) {
      container.innerHTML = '<div class="empty-state">Todavia no hay tweets publicados ni fallidos.</div>';
      return;
    }
    container.innerHTML = items.map(historyCardHtml).join("");
    items.filter((i) => i.status === "failed").forEach((i) => bindRetryButton(i));
    bindHistoryCopyButtons(items);
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Error cargando historial: ${escapeHtml(e.message)}</div>`;
  }
}

function historyCardHtml(tweet) {
  const badgeClass = tweet.status === "published" ? "badge-published" : "badge-failed";
  const label = tweet.status === "published" ? "Publicado" : "Fallido";
  const link =
    tweet.status === "published" && tweet.tweet_id
      ? `<a href="https://x.com/i/web/status/${tweet.tweet_id}" target="_blank" rel="noopener">Ver en X</a>`
      : "";
  const error = tweet.error_message ? `<div class="card-error">${escapeHtml(tweet.error_message)}</div>` : "";
  const retryBtn = tweet.status === "failed" ? `<button class="retry-btn" data-id="${tweet.id}">Reintentar</button>` : "";
  const image = tweet.image_url ? `<img class="image-preview" src="${escapeHtml(tweet.image_url)}" />` : "";
  return `
    <div class="card" data-id="${tweet.id}">
      <div class="card-header">
        <span class="badge ${badgeClass}">${label}</span>
        <span class="card-meta">${formatDate(tweet.published_at || tweet.created_at)}</span>
      </div>
      <div class="card-content">${escapeHtml(tweet.content)}</div>
      ${image}
      ${error}
      <div class="card-actions">${link}<button class="copy-history-btn" data-id="${tweet.id}">Copiar</button>${retryBtn}</div>
    </div>
  `;
}

function bindRetryButton(tweet) {
  const btn = document.querySelector(`#history-list .retry-btn[data-id="${tweet.id}"]`);
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      await api(`/api/tweets/${tweet.id}/retry`, { method: "POST" });
      switchTab("drafts");
    } catch (e) {
      alert(e.message);
    }
  });
}

function bindHistoryCopyButtons(items) {
  items.forEach((tweet) => {
    const btn = document.querySelector(`#history-list .copy-history-btn[data-id="${tweet.id}"]`);
    if (btn) bindCopyButton(btn, () => tweet.content);
  });
}

// ---------- Templates tab ----------
function initTemplateForm() {
  document.getElementById("template-save-btn").addEventListener("click", handleTemplateFormSave);
  document.getElementById("template-cancel-edit-btn").addEventListener("click", resetTemplateForm);
}

function resetTemplateForm() {
  document.getElementById("template-form-id").value = "";
  document.getElementById("template-form-name").value = "";
  document.getElementById("template-form-text").value = "";
  document.getElementById("template-cancel-edit-btn").hidden = true;
}

async function handleTemplateFormSave() {
  const id = document.getElementById("template-form-id").value;
  const name = document.getElementById("template-form-name").value.trim();
  const template_text = document.getElementById("template-form-text").value.trim();
  if (!name || !template_text) {
    alert("Nombre y texto de la plantilla son obligatorios.");
    return;
  }
  try {
    if (id) {
      await api(`/api/templates/${id}`, { method: "PUT", body: JSON.stringify({ name, template_text }) });
    } else {
      await api("/api/templates", { method: "POST", body: JSON.stringify({ name, template_text }) });
    }
    resetTemplateForm();
    loadTemplatesTab();
    loadTemplateSelect();
  } catch (e) {
    alert(e.message);
  }
}

async function loadTemplatesTab() {
  const container = document.getElementById("templates-list");
  container.innerHTML = "Cargando...";
  try {
    const templates = await api("/api/templates");
    if (!templates.length) {
      container.innerHTML = '<div class="empty-state">No hay plantillas todavia.</div>';
      return;
    }
    container.innerHTML = templates.map(templateCardHtml).join("");
    templates.forEach((t) => bindTemplateCard(t));
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Error cargando plantillas: ${escapeHtml(e.message)}</div>`;
  }
}

function templateCardHtml(template) {
  return `
    <div class="card" data-id="${template.id}">
      <div class="card-header">
        <strong>${escapeHtml(template.name)}</strong>
        <span class="card-meta">${formatDate(template.created_at)}</span>
      </div>
      <div class="card-content">${escapeHtml(template.template_text)}</div>
      <div class="card-actions">
        <button class="edit-template-btn">Editar</button>
        <button class="delete-template-btn">Eliminar</button>
      </div>
    </div>
  `;
}

function bindTemplateCard(template) {
  const card = document.querySelector(`#templates-list .card[data-id="${template.id}"]`);
  card.querySelector(".edit-template-btn").addEventListener("click", () => {
    document.getElementById("template-form-id").value = template.id;
    document.getElementById("template-form-name").value = template.name;
    document.getElementById("template-form-text").value = template.template_text;
    document.getElementById("template-cancel-edit-btn").hidden = false;
  });
  card.querySelector(".delete-template-btn").addEventListener("click", async () => {
    if (!confirm("¿Eliminar esta plantilla?")) return;
    try {
      await api(`/api/templates/${template.id}`, { method: "DELETE" });
      loadTemplatesTab();
      loadTemplateSelect();
    } catch (e) {
      alert(e.message);
    }
  });
}

// ---------- Sesion ----------
async function initLogout() {
  try {
    const status = await api("/api/auth/status");
    if (!status.enabled) return;
    const btn = document.getElementById("logout-btn");
    btn.hidden = false;
    btn.addEventListener("click", async () => {
      await api("/api/auth/logout", { method: "POST" });
      window.location.replace("/login");
    });
  } catch (e) {
    // silencioso: sin boton de salir, el resto de la app sigue andando
  }
}

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCompose();
  initTemplateForm();
  checkConfig();
  initLogout();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
