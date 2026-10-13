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
  if (!res.ok) {
    const message = body?.detail || `Error ${res.status}`;
    throw new Error(message);
  }
  return body;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
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

// Boton "Guardar" de las tarjetas de resultado (H2H, Efemeride, Cruce LEC,
// Lote): ninguno de esos modos auto-guarda -- el usuario elige que
// variante(s) quedan como borrador, con el mismo endpoint que usa el
// "Guardar borrador" del compose compartido.
function bindSaveButton(button, getText, source) {
  button.addEventListener("click", async () => {
    try {
      await api("/api/tweets", { method: "POST", body: JSON.stringify({ content: getText(), source }) });
      flashButtonLabel(button, "Guardado!");
    } catch (e) {
      alert(e.message);
    }
  });
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
    if (!cfg.anthropic_configured) missing.push("Anthropic (IA)");
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

  document.getElementById("ai-generate-btn").addEventListener("click", handleAiGenerate);
  document.getElementById("template-render-btn").addEventListener("click", handleTemplateRender);
  document.getElementById("save-draft-btn").addEventListener("click", () => handleSave(false));
  document.getElementById("publish-now-btn").addEventListener("click", () => handleSave(true));
  document.getElementById("batch-generate-btn").addEventListener("click", handleBatchGenerate);
  document.getElementById("calendar-generate-btn").addEventListener("click", handleCalendarGenerate);
  document.getElementById("stats-generate-btn").addEventListener("click", handleStatsGenerate);
  document.getElementById("h2h-autofill-btn").addEventListener("click", handleH2hAutofill);
  document.getElementById("h2h-generate-btn").addEventListener("click", handleH2hGenerate);
  document.getElementById("duel-autofill-btn").addEventListener("click", handleDuelAutofill);
  document.getElementById("duel-generate-btn").addEventListener("click", handleDuelGenerate);
  document.getElementById("anniversary-generate-btn").addEventListener("click", handleAnniversaryGenerate);
  document.getElementById("lec-compare-generate-btn").addEventListener("click", handleLecCompareGenerate);
  bindCopyButton(document.getElementById("copy-content-btn"), () => document.getElementById("compose-content").value);

  loadTemplateSelect();
  loadTeamOptions([
    "rivalry-team-a",
    "rivalry-team-b",
    "h2h-team-a",
    "h2h-team-b",
    "ranked-team-a",
    "ranked-team-b",
    "duel-team-a",
    "duel-team-b",
  ]);
}

async function loadTeamOptions(selectIds) {
  try {
    const teams = await api("/api/generate/stats/teams");
    const options = teams.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    selectIds.forEach((id) => document.getElementById(id).insertAdjacentHTML("beforeend", options));
  } catch (e) {
    // silencioso: si gol.gg no responde, el usuario todavia puede usar el resto de la app
  }
}

function updateComposeMode() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  document.getElementById("mode-calendar").hidden = mode !== "calendar";
  document.getElementById("mode-stats").hidden = mode !== "stats";
  document.getElementById("mode-h2h").hidden = mode !== "h2h";
  document.getElementById("mode-duel").hidden = mode !== "duel";
  document.getElementById("mode-anniversary").hidden = mode !== "anniversary";
  document.getElementById("mode-lec-compare").hidden = mode !== "lec-compare";
  document.getElementById("mode-ai").hidden = mode !== "ai";
  document.getElementById("mode-batch").hidden = mode !== "batch";
  document.getElementById("mode-template").hidden = mode !== "template";
  document.getElementById("mode-manual").hidden = mode !== "manual";
  document.getElementById("single-compose-area").hidden =
    mode === "batch" || mode === "h2h" || mode === "duel" || mode === "anniversary" || mode === "lec-compare";
}

async function handleLecCompareGenerate() {
  const style = document.querySelector('input[name="lec-compare-style"]:checked').value;
  const focus = document.getElementById("lec-compare-focus").value.trim();
  const resultsEl = document.getElementById("lec-compare-results");

  const btn = document.getElementById("lec-compare-generate-btn");
  btn.disabled = true;
  resultsEl.innerHTML = "Consultando gol.gg (LES y LEC)...";
  try {
    const results = await api("/api/generate/league-comparison", {
      method: "POST",
      body: JSON.stringify({ style, focus: focus || null }),
    });
    resultsEl.innerHTML = results.map(lecCompareResultCardHtml).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindCopyButton(card.querySelector(".copy-lec-compare-btn"), () => r.content);
        bindSaveButton(card.querySelector(".save-lec-compare-btn"), () => r.content, "lec-compare");
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function lecCompareResultCardHtml(result) {
  const toneLabel = result.tone === "debate" ? "Tono: pregunta a debate" : "Tono: dato sorprendente";
  if (result.error) {
    return `
      <div class="card">
        <div class="card-meta">${toneLabel}</div>
        <div class="card-error">${escapeHtml(result.error)}</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-meta">${toneLabel} · ${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      <div class="card-content">${escapeHtml(result.content)}</div>
      <div class="card-actions">
        <button class="save-lec-compare-btn">Guardar</button>
        <button class="copy-lec-compare-btn">Copiar</button>
      </div>
    </div>
  `;
}

async function handleAnniversaryGenerate() {
  const style = document.querySelector('input[name="anniversary-style"]:checked').value;
  const resultsEl = document.getElementById("anniversary-results");

  const btn = document.getElementById("anniversary-generate-btn");
  btn.disabled = true;
  resultsEl.innerHTML = "Buscando efemeride...";
  try {
    const results = await api("/api/generate/anniversary", {
      method: "POST",
      body: JSON.stringify({ style }),
    });
    resultsEl.innerHTML = results.map(anniversaryResultCardHtml).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindCopyButton(card.querySelector(".copy-anniversary-btn"), () => r.content);
        bindSaveButton(card.querySelector(".save-anniversary-btn"), () => r.content, "anniversary");
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function anniversaryResultCardHtml(result) {
  const formatLabel = result.format === "completo" ? "Version completa" : "Dato rapido";
  const exactNote = result.is_exact ? "" : " (no es de hoy exacto, ver texto)";
  if (result.error) {
    return `
      <div class="card">
        <div class="card-meta">${formatLabel}${exactNote}</div>
        <div class="card-error">${escapeHtml(result.error)}</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-meta">${formatLabel}${exactNote} · ${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      <div class="card-content">${escapeHtml(result.content)}</div>
      <div class="card-actions">
        <button class="save-anniversary-btn">Guardar</button>
        <button class="copy-anniversary-btn">Copiar</button>
      </div>
    </div>
  `;
}

async function handleH2hAutofill() {
  const feedback = document.getElementById("h2h-autofill-feedback");
  feedback.textContent = "Consultando calendario de hoy...";
  try {
    const matches = await api("/api/generate/stats/today-match");
    if (matches.length === 0) {
      feedback.textContent = "No hay partido de LES programado para hoy.";
    } else if (matches.length === 1) {
      document.getElementById("h2h-team-a").value = matches[0].team_a;
      document.getElementById("h2h-team-b").value = matches[0].team_b;
      feedback.textContent = `Completado: ${matches[0].team_a} vs ${matches[0].team_b} (${matches[0].block_name}).`;
    } else {
      const list = matches.map((m) => `${m.team_a} vs ${m.team_b}`).join(", ");
      feedback.textContent = `Hay varios partidos hoy, elegi los equipos a mano: ${list}.`;
    }
  } catch (e) {
    feedback.textContent = e.message;
  }
}

async function handleH2hGenerate() {
  const teamA = document.getElementById("h2h-team-a").value;
  const teamB = document.getElementById("h2h-team-b").value;
  const resultsEl = document.getElementById("h2h-results");
  if (!teamA || !teamB) {
    resultsEl.innerHTML = '<div class="empty-state">Elegi los dos equipos.</div>';
    return;
  }

  const style = document.querySelector('input[name="h2h-style"]:checked').value;

  const btn = document.getElementById("h2h-generate-btn");
  btn.disabled = true;
  resultsEl.innerHTML = "Generando...";
  try {
    const results = await api("/api/generate/stats/head-to-head-preview", {
      method: "POST",
      body: JSON.stringify({ team_a: teamA, team_b: teamB, style }),
    });
    resultsEl.innerHTML = results.map(h2hResultCardHtml).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindCopyButton(card.querySelector(".copy-h2h-btn"), () => r.content);
        bindSaveButton(card.querySelector(".save-h2h-btn"), () => r.content, "h2h");
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function h2hResultCardHtml(result) {
  const angleLabel = result.angle === "historial" ? "Enfoque: historial" : "Enfoque: forma reciente";
  if (result.error) {
    return `
      <div class="card">
        <div class="card-meta">${angleLabel}</div>
        <div class="card-error">${escapeHtml(result.error)}</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-meta">${angleLabel} · ${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      <div class="card-content">${escapeHtml(result.content)}</div>
      <div class="card-actions">
        <button class="save-h2h-btn">Guardar</button>
        <button class="copy-h2h-btn">Copiar</button>
      </div>
    </div>
  `;
}

async function handleDuelAutofill() {
  const feedback = document.getElementById("duel-autofill-feedback");
  feedback.textContent = "Consultando calendario de hoy/mañana...";
  try {
    const matches = await api("/api/generate/duel/today-match");
    if (matches.length === 0) {
      feedback.textContent = "No hay partido de LES programado para hoy ni mañana.";
    } else if (matches.length === 1) {
      document.getElementById("duel-team-a").value = matches[0].team_a;
      document.getElementById("duel-team-b").value = matches[0].team_b;
      feedback.textContent = `Completado: ${matches[0].team_a} vs ${matches[0].team_b} (${matches[0].block_name}).`;
    } else {
      const list = matches.map((m) => `${m.team_a} vs ${m.team_b}`).join(", ");
      feedback.textContent = `Hay varios partidos, elegi los equipos a mano: ${list}.`;
    }
  } catch (e) {
    feedback.textContent = e.message;
  }
}

async function handleDuelGenerate() {
  const teamA = document.getElementById("duel-team-a").value;
  const teamB = document.getElementById("duel-team-b").value;
  const resultsEl = document.getElementById("duel-results");
  if (!teamA || !teamB) {
    resultsEl.innerHTML = '<div class="empty-state">Elegi los dos equipos.</div>';
    return;
  }

  const style = document.querySelector('input[name="duel-style"]:checked').value;

  const btn = document.getElementById("duel-generate-btn");
  btn.disabled = true;
  resultsEl.innerHTML = "Generando...";
  try {
    const results = await api("/api/generate/duel", {
      method: "POST",
      body: JSON.stringify({ team_a: teamA, team_b: teamB, style }),
    });
    if (!results.length) {
      resultsEl.innerHTML =
        '<div class="empty-state">No hay ningun carril con datos suficientes en ambos equipos para armar un duelo.</div>';
      return;
    }
    resultsEl.innerHTML = results.map(duelResultCardHtml).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindCopyButton(card.querySelector(".copy-duel-btn"), () => r.content);
        bindSaveButton(card.querySelector(".save-duel-btn"), () => r.content, "duel");
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function duelResultCardHtml(result) {
  const meta = `${result.role} · ${result.subject}`;
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
      <div class="card-actions">
        <button class="save-duel-btn">Guardar</button>
        <button class="copy-duel-btn">Copiar</button>
      </div>
    </div>
  `;
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
  const style = document.querySelector('input[name="stats-style"]:checked').value;
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
      style,
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

  if (!leagues.length) {
    setComposeFeedback("Marca al menos una liga (LES o LEC).", true);
    return;
  }
  const style = document.querySelector('input[name="calendar-style"]:checked').value;

  setComposeFeedback("Consultando calendario...", false);
  await fillComposeFromGenerate(
    "/api/generate/calendar",
    { leagues, style },
    "Calendario generado. Podes editarlo antes de guardar o publicar."
  );
}

async function handleBatchGenerate() {
  const topics = document
    .getElementById("batch-topics")
    .value.split("\n")
    .map((t) => t.trim())
    .filter(Boolean);
  const resultsEl = document.getElementById("batch-results");
  if (!topics.length) {
    resultsEl.innerHTML = '<div class="empty-state">Ingresa al menos un tema, uno por linea.</div>';
    return;
  }
  const tone = document.getElementById("batch-tone").value.trim();
  const instructions = document.getElementById("batch-instructions").value.trim();

  const btn = document.getElementById("batch-generate-btn");
  btn.disabled = true;
  resultsEl.innerHTML = "Generando...";
  try {
    const results = await api("/api/generate/ai/batch", {
      method: "POST",
      body: JSON.stringify({ topics, tone: tone || null, instructions: instructions || null }),
    });
    resultsEl.innerHTML = results.map(batchResultCardHtml).join("");
    results.forEach((r, idx) => {
      if (r.content) {
        const card = resultsEl.children[idx];
        bindCopyButton(card.querySelector(".copy-batch-btn"), () => r.content);
        bindSaveButton(card.querySelector(".save-batch-btn"), () => r.content, "batch");
      }
    });
  } catch (e) {
    resultsEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function batchResultCardHtml(result) {
  if (result.error) {
    return `
      <div class="card">
        <div class="card-meta">Tema: ${escapeHtml(result.topic)}</div>
        <div class="card-error">${escapeHtml(result.error)}</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-meta">Tema: ${escapeHtml(result.topic)} · ${result.char_count} / ${TWEET_CHAR_LIMIT}</div>
      <div class="card-content">${escapeHtml(result.content)}</div>
      <div class="card-actions">
        <button class="save-batch-btn">Guardar</button>
        <button class="copy-batch-btn">Copiar</button>
      </div>
    </div>
  `;
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
// en el editor (IA, Calendario, Stats, Plantilla): pegarle al endpoint,
// llenar compose-content, y mostrar feedback de exito/error.
async function fillComposeFromGenerate(endpoint, payload, successMessage) {
  try {
    const result = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("compose-content").value = result.content;
    updateCharCounter();
    setComposeFeedback(successMessage, false);
  } catch (e) {
    setComposeFeedback(e.message, true);
  }
}

async function handleAiGenerate() {
  const topic = document.getElementById("ai-topic").value.trim();
  if (!topic) {
    setComposeFeedback("Ingresa un tema para generar el tweet.", true);
    return;
  }
  const tone = document.getElementById("ai-tone").value.trim();
  const instructions = document.getElementById("ai-instructions").value.trim();
  setComposeFeedback("Generando...", false);
  await fillComposeFromGenerate(
    "/api/generate/ai",
    { topic, tone: tone || null, instructions: instructions || null },
    "Tweet generado. Podes editarlo antes de guardar o publicar."
  );
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

  try {
    const tweet = await api("/api/tweets", {
      method: "POST",
      body: JSON.stringify({ content, source: mode }),
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
  document.getElementById("ai-topic").value = "";
  document.getElementById("ai-tone").value = "";
  document.getElementById("ai-instructions").value = "";
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
        <span class="card-meta">${formatDate(tweet.created_at)} · ${tweet.source}</span>
      </div>
      <textarea class="card-edit" rows="3">${escapeHtml(tweet.content)}</textarea>
      <div class="char-counter draft-char-counter">0 / 280</div>
      <div class="card-actions">
        <button class="save-edit-btn">Guardar cambios</button>
        <button class="copy-draft-btn">Copiar</button>
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

  bindCopyButton(card.querySelector(".copy-draft-btn"), () => textarea.value);

  card.querySelector(".save-edit-btn").addEventListener("click", async () => {
    try {
      await api(`/api/tweets/${tweet.id}`, {
        method: "PUT",
        body: JSON.stringify({ content: textarea.value }),
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
        body: JSON.stringify({ content: textarea.value }),
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
  return `
    <div class="card" data-id="${tweet.id}">
      <div class="card-header">
        <span class="badge ${badgeClass}">${label}</span>
        <span class="card-meta">${formatDate(tweet.published_at || tweet.created_at)}</span>
      </div>
      <div class="card-content">${escapeHtml(tweet.content)}</div>
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

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCompose();
  initTemplateForm();
  checkConfig();
});
