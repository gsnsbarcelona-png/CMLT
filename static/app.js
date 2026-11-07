const TWEET_CHAR_LIMIT = 280;
const URL_PLACEHOLDER_LEN = 23;
const URL_PATTERN = /https?:\/\/\S+/g;

function countChars(text) {
  const urls = text.match(URL_PATTERN) || [];
  const withoutUrls = text.replace(URL_PATTERN, "");
  return Array.from(withoutUrls).length + urls.length * URL_PLACEHOLDER_LEN;
}

// Aviso de "servidor despertando": en el plan gratuito de Render el servicio
// se duerme y la primera peticion puede tardar hasta un minuto. Si algo lleva
// mas de 4 s se muestra un aviso (en vez de parecer que la app esta colgada).
let pendingRequests = 0;
let slowNoticeTimer = null;

function noteRequestStart() {
  pendingRequests += 1;
  if (!slowNoticeTimer) {
    slowNoticeTimer = setTimeout(() => {
      const el = document.getElementById("slow-notice");
      if (el && pendingRequests > 0) el.hidden = false;
    }, 4000);
  }
}

function noteRequestEnd() {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (pendingRequests === 0) {
    clearTimeout(slowNoticeTimer);
    slowNoticeTimer = null;
    const el = document.getElementById("slow-notice");
    if (el) el.hidden = true;
  }
}

async function api(path, options = {}) {
  noteRequestStart();
  try {
    return await apiRequest(path, options);
  } finally {
    noteRequestEnd();
  }
}

async function apiRequest(path, options) {
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

// Boton "Compartir": hoja nativa del movil (X, WhatsApp, etc.) via Web Share
// API. Solo aparece si el navegador la soporta. Si hay una imagen propia
// (/data/images/...) la adjunta como archivo, cosa que el enlace de "Abrir en
// X" no puede; las imagenes externas (escudos) no se adjuntan.
function bindShareButton(button, getText, getImageUrl) {
  if (!button || !navigator.share) return;
  button.hidden = false;
  button.addEventListener("click", async () => {
    const text = getText();
    if (!text || !text.trim()) return;
    const data = { text };
    try {
      const imageUrl = getImageUrl ? getImageUrl() : "";
      if (imageUrl && imageUrl.startsWith("/data/images/")) {
        const blob = await (await fetch(imageUrl)).blob();
        const file = new File([blob], imageUrl.split("/").pop(), { type: blob.type });
        if (navigator.canShare && navigator.canShare({ files: [file] })) data.files = [file];
      }
      await navigator.share(data);
    } catch (e) {
      if (e.name !== "AbortError") flashButtonLabel(button, "No se pudo compartir");
    }
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
      <div class="card-meta">${escapeHtml(meta)}</div>
      <textarea class="card-edit card-edit-result" rows="5" aria-label="Texto del tweet (editable)">${escapeHtml(result.content)}</textarea>
      <div class="char-counter result-char-counter">${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      ${imagePickerHtml()}
      <div class="card-actions">
        <button class="save-${source}-btn">Guardar</button>
        <button class="copy-${source}-btn">Copiar</button>
        <button class="open-x-${source}-btn" title="Abre X con el texto listo (sin imagen)">Abrir en X</button>
        <button class="share-${source}-btn" hidden>Compartir</button>
      </div>
    </div>
  `;
}

async function generateResultCards({
  endpoint,
  payload,
  fetchResults,
  resultsElId,
  btnId,
  source,
  metaFn,
  loadingText,
  emptyMessage,
}) {
  const resultsEl = document.getElementById(resultsElId);
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  resultsEl.innerHTML = loadingText;
  try {
    const results = fetchResults
      ? await fetchResults()
      : await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    if (!results.length && emptyMessage) {
      resultsEl.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
      return;
    }
    resultsEl.innerHTML = results.map((r) => variantResultCardHtml(r, source, metaFn)).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindImagePicker(card, { suggestedTeams: r.suggested_teams || [] });
        // El texto es editable: todos los botones leen lo que haya en el textarea.
        const textarea = card.querySelector(".card-edit-result");
        const counter = card.querySelector(".result-char-counter");
        const getText = () => textarea.value;
        textarea.addEventListener("input", () => updateCounterEl(counter, getText()));
        bindCopyButton(card.querySelector(`.copy-${source}-btn`), getText);
        bindOpenXButton(card.querySelector(`.open-x-${source}-btn`), getText);
        bindShareButton(card.querySelector(`.share-${source}-btn`), getText, () => card.dataset.imageUrl);
        bindSaveButton(card.querySelector(`.save-${source}-btn`), getText, source, () => card.dataset.imageUrl);
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

// ---------- Tabs ----------
function updateCounterEl(counterEl, text) {
  const count = countChars(text);
  counterEl.textContent = `${count} / ${TWEET_CHAR_LIMIT}`;
  counterEl.classList.remove("warn", "over");
  if (count > TWEET_CHAR_LIMIT) counterEl.classList.add("over");
  else if (count > 260) counterEl.classList.add("warn");
}

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
    b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "drafts") loadDrafts();
  if (name === "history") loadHistory();
}

// ---------- Config banner ----------
async function checkConfig() {
  try {
    const cfg = await api("/api/config/check");
    const banner = document.getElementById("config-banner");
    const missing = [];
    if (!cfg.x_configured) missing.push("X (publicacion)");
    if (missing.length) {
      banner.textContent = `Sin configurar: ${missing.join(", ")}. Puedes usar "Abrir en X" o "Copiar".`;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch (e) {
    // silencioso: si /api/config/check falla, no bloqueamos la UI
  }
}

// ---------- Compose ----------
// Recordar el ultimo modo, ligas, alcance, etc. (solo en este navegador):
// ahorra 1-3 toques por sesion en el movil. localStorage puede no estar
// disponible (ventana privada), asi que todo va envuelto en try/catch y la app
// funciona igual sin el.
const PREFS_KEY = "ta-prefs";
const PREF_SELECTOR = "#tab-compose input:not([type=file]):not([type=text]), #tab-compose select";

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
  } catch (e) {
    return {};
  }
}

function prefKey(el) {
  if (el.type === "radio") return el.name ? `r:${el.name}` : null;
  return el.id ? `i:${el.id}` : null;
}

function applyPref(el, prefs) {
  const key = prefKey(el);
  if (!key || !(key in prefs)) return;
  if (el.type === "radio") el.checked = el.value === prefs[key];
  else if (el.type === "checkbox") el.checked = !!prefs[key];
  else if (el.tagName === "SELECT") {
    if ([...el.options].some((o) => o.value === prefs[key])) el.value = prefs[key];
  }
}

function applyPrefs() {
  const prefs = loadPrefs();
  document.querySelectorAll(PREF_SELECTOR).forEach((el) => applyPref(el, prefs));
}

function trackPrefs() {
  document.getElementById("tab-compose").addEventListener("change", (event) => {
    const el = event.target;
    if (!el.matches(PREF_SELECTOR)) return;
    const key = prefKey(el);
    if (!key) return;
    try {
      const prefs = loadPrefs();
      prefs[key] = el.type === "checkbox" ? el.checked : el.value;
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch (e) {
      // sin localStorage: no se recuerda nada, la app sigue igual
    }
  });
}

function initCompose() {
  applyPrefs();
  trackPrefs();
  const modeRadios = document.querySelectorAll('input[name="mode"]');
  modeRadios.forEach((r) => r.addEventListener("change", updateComposeMode));
  updateComposeMode();

  const contentEl = document.getElementById("compose-content");
  contentEl.addEventListener("input", updateCharCounter);
  updateCharCounter();

  document.getElementById("image-picker").innerHTML = imagePickerHtml();
  bindImagePicker(document.getElementById("image-picker"));
  document.getElementById("save-draft-btn").addEventListener("click", () => handleSave(false));
  document.getElementById("publish-now-btn").addEventListener("click", () => handleSave(true));
  document.getElementById("calendar-generate-btn").addEventListener("click", handleCalendarGenerate);
  document.getElementById("results-generate-btn").addEventListener("click", handleResultsGenerate);
  document.getElementById("match-day-generate-btn").addEventListener("click", handleMatchDayPack);
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
  bindShareButton(
    document.getElementById("share-btn"),
    () => document.getElementById("compose-content").value,
    () => document.getElementById("image-picker").dataset.imageUrl || ""
  );

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
    const prefs = loadPrefs();
    selectIds.forEach((id) => {
      const select = document.getElementById(id);
      select.insertAdjacentHTML("beforeend", options);
      applyPref(select, prefs); // recuperar el equipo elegido la ultima vez
    });
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
  document.getElementById("mode-match-day").hidden = mode !== "match-day";
  document.getElementById("mode-results").hidden = mode !== "results";
  document.getElementById("mode-stats").hidden = mode !== "stats";
  document.getElementById("mode-h2h").hidden = mode !== "h2h";
  document.getElementById("mode-duel").hidden = mode !== "duel";
  document.getElementById("mode-top-ranking").hidden = mode !== "top-ranking";
  document.getElementById("mode-anniversary").hidden = mode !== "anniversary";
  document.getElementById("mode-lec-compare").hidden = mode !== "lec-compare";
  document.getElementById("mode-manual").hidden = mode !== "manual";
  document.getElementById("single-compose-area").hidden =
    mode === "match-day" ||
    mode === "h2h" ||
    mode === "duel" ||
    mode === "top-ranking" ||
    mode === "anniversary" ||
    mode === "lec-compare";
}

async function handleResultsGenerate() {
  const leagues = [];
  if (document.getElementById("results-les").checked) leagues.push("les");
  if (document.getElementById("results-lec").checked) leagues.push("lec");
  if (document.getElementById("results-emea-masters").checked) leagues.push("emea_masters");

  if (!leagues.length) {
    setComposeFeedback("Marca al menos una liga.", true);
    return;
  }
  setComposeFeedback("Consultando resultados...", false);
  await fillComposeFromGenerate(
    "/api/generate/results",
    { leagues },
    "Resultados generados. Puedes editarlos antes de guardar o publicar."
  );
}

// Pack "dia de partido": en un clic, el calendario de la semana + la preview
// H2H (2 variantes) de CADA partido de LES de hoy. Reutiliza los endpoints
// existentes (nada nuevo en el servidor). Los nombres de equipo de lolesports
// se reconcilian con los de gol.gg (mismo criterio que "Autocompletar").
async function handleMatchDayPack() {
  await generateResultCards({
    resultsElId: "match-day-results",
    btnId: "match-day-generate-btn",
    source: "match-day",
    metaFn: (r) => r._meta,
    loadingText: "Preparando el pack del dia...",
    emptyMessage: "Hoy no hay partidos de LES. Prueba Resultados, Efemeride o Top/Ranking.",
    fetchResults: async () => {
      const matches = await api("/api/generate/stats/today-match");
      if (!matches.length) return [];
      const golTeams = await api("/api/generate/stats/h2h-teams").catch(() => []);
      const toGolName = (name) => {
        const wanted = normalizeTeamName(name);
        return (
          golTeams.find((t) => {
            const norm = normalizeTeamName(t);
            return norm === wanted || norm.includes(wanted) || wanted.includes(norm);
          }) || name
        );
      };
      const out = [];
      const calendar = await api("/api/generate/calendar", { method: "POST", body: JSON.stringify({ leagues: ["les"] }) });
      out.push({ ...calendar, _meta: "Calendario de la semana" });
      for (const m of matches) {
        const teamA = toGolName(m.team_a);
        const teamB = toGolName(m.team_b);
        try {
          const variants = await api("/api/generate/stats/head-to-head-preview", {
            method: "POST",
            body: JSON.stringify({ team_a: teamA, team_b: teamB }),
          });
          variants.forEach((v) =>
            out.push({ ...v, _meta: `${teamA} vs ${teamB} · ${v.angle === "historial" ? "historial" : "forma reciente"}` })
          );
        } catch (e) {
          out.push({ content: null, error: `${teamA} vs ${teamB}: ${e.message}`, _meta: "H2H no disponible" });
        }
      }
      return out;
    },
  });
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
// en el editor (Calendario, Stats): pegarle al endpoint,
// llenar compose-content, y mostrar feedback de exito/error.
async function fillComposeFromGenerate(endpoint, payload, successMessage) {
  const generateButtons = document.querySelectorAll("#tab-compose button[id$='-generate-btn']");
  generateButtons.forEach((b) => (b.disabled = true));
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
  } finally {
    generateButtons.forEach((b) => (b.disabled = false));
  }
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
        <button class="share-draft-btn" hidden>Compartir</button>
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
  bindShareButton(card.querySelector(".share-draft-btn"), () => textarea.value, () => card.dataset.imageUrl || "");

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

async function showVersion() {
  const el = document.getElementById("app-version");
  try {
    const v = await api("/api/version");
    const when = new Date(v.started_at).toLocaleString();
    let status = "";
    if (v.up_to_date === true) status = ' · <span class="version-ok">✓ ultima version</span>';
    else if (v.up_to_date === false) {
      status = ` · <span class="version-old">hay una nueva (${escapeHtml(v.latest)}), recarga en unos minutos</span>`;
    }
    el.innerHTML = `Version ${escapeHtml(v.commit)} · iniciada ${escapeHtml(when)}${status}`;
  } catch (e) {
    // silencioso: la version es informativa, no bloquea la app
  }
}

function initBackup() {
  const feedback = document.getElementById("backup-feedback");
  const fileInput = document.getElementById("backup-import-file");
  const say = (text) => {
    feedback.textContent = text;
  };

  document.getElementById("backup-export-btn").addEventListener("click", async () => {
    try {
      const data = await api("/api/backup");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `tweet-automation-backup-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      say(`Descargados ${data.tweets.length} tweets.`);
    } catch (e) {
      say(`Error: ${e.message}`);
    }
  });

  document.getElementById("backup-import-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      const body = JSON.parse(await file.text());
      const res = await api("/api/restore", { method: "POST", body: JSON.stringify(body) });
      say(`Restaurado: ${res.tweets_added} tweets nuevos.`);
      loadDrafts();
    } catch (e) {
      say(`Error: ${e.message}`);
    } finally {
      fileInput.value = "";
    }
  });
}

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCompose();
  checkConfig();
  showVersion();
  initBackup();
  initLogout();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
