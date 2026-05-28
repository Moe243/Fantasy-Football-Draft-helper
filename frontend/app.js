const state = {
  players: [],
  settings: null,
  keepers: [],
  picks: [],
  recommendations: [],
  waiverGroups: {},
  playerSource: "sample",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

async function loadAll() {
  const [players, settings, keepers, picks, draft] = await Promise.all([
    api("/api/players"),
    api("/api/league/settings"),
    api("/api/keepers"),
    api("/api/draft/picks"),
    api("/api/draft/recommendations"),
  ]);
  state.players = players.players;
  state.playerSource = players.source;
  state.settings = settings;
  state.keepers = keepers.keepers;
  state.picks = picks.picks;
  state.recommendations = draft.recommendations;
  state.currentPick = draft.current_pick;
  renderAll();
  await refreshWaivers();
}

function renderAll() {
  renderStatus();
  renderPlayerOptions();
  renderRecommendations();
  renderPicks();
  renderKeepers();
  renderWaivers();
}

function renderStatus() {
  $("#status-scoring").textContent = state.settings?.scoring || "PPR";
  $("#status-teams").textContent = state.settings?.teams || "10";
  $("#status-slot").textContent = state.settings?.draft_slot || "6";
  $("#settings-teams").value = state.settings?.teams || 10;
  $("#settings-slot").value = state.settings?.draft_slot || 6;
  $("#settings-scoring").value = state.settings?.scoring || "PPR";
  $("#current-pick").textContent = `Pick ${state.currentPick || 1}`;
}

function renderPlayerOptions() {
  $("#player-options").innerHTML = state.players
    .map((player) => `<option value="${escapeHtml(player.name || player.full_name)}">${player.position} · ${player.team}</option>`)
    .join("");
}

function renderRecommendations() {
  const container = $("#recommendations");
  if (!state.recommendations.length) {
    container.innerHTML = emptyState("No recommendations available. Clear picks or keepers to reset the board.");
    return;
  }
  container.innerHTML = state.recommendations
    .map((item) => {
      const player = item.player;
      const playerName = player.name || player.full_name;
      const risk = player.injury_status && !["Healthy", "Active"].includes(player.injury_status)
        ? `<span class="tag risk">${escapeHtml(player.injury_status)}</span>`
        : "";
      return `
        <article class="recommendation-card">
          <div>
            <div class="player-title">
              <strong>${escapeHtml(playerName)}</strong>
              <span class="tag position">${player.position} · ${player.team}</span>
              <span class="tag fit">${escapeHtml(item.fit)}</span>
              ${risk}
            </div>
            ${renderConsensusGrid(item)}
            <ul class="reason-list">
              ${item.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
            </ul>
            <div class="card-actions">
              <button class="small-button" data-draft-me="${player.id || player.internal_player_id}">Draft to me</button>
              <button class="small-button" data-draft-taken="${player.id || player.internal_player_id}">Mark taken</button>
            </div>
          </div>
          <div class="score-box">
            <span>Score</span>
            <strong>${item.score}</strong>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderConsensusGrid(item) {
  if (!item.consensus) return "";
  const consensus = item.consensus;
  return `
    <div class="consensus-grid">
      ${metricCell("Consensus", formatMetric(consensus.consensus_rank))}
      ${metricCell("Sleeper ADP", formatMetric(consensus.sleeper_adp))}
      ${metricCell("FantasyPros", formatMetric(consensus.fantasypros_rank))}
      ${metricCell("ESPN", formatMetric(consensus.espn_rank))}
      ${metricCell("Projected", formatMetric(consensus.projected_points_avg))}
      ${metricCell("Label", consensus.label || "None")}
      ${metricCell("Sources", consensus.source_count ?? 0)}
      ${metricCell("Spread", formatMetric(consensus.rank_spread))}
    </div>
  `;
}

function metricCell(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function formatMetric(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return String(value);
}

function renderPicks() {
  const container = $("#draft-picks");
  $("#pick-number").placeholder = String((state.picks.at(-1)?.pick_no || 0) + 1);
  if (!state.picks.length) {
    container.innerHTML = emptyState("No draft picks marked yet.");
    return;
  }
  container.innerHTML = state.picks
    .map((pick) => `
      <div class="compact-row">
        <div>
          <strong>${pick.pick_no}. ${escapeHtml(pick.player?.name || pick.player?.full_name || pick.player_id)}</strong>
          <span>${escapeHtml(pick.manager)} · ${escapeHtml(pick.player?.position || "")}</span>
        </div>
        <button class="text-button" data-remove-pick="${pick.pick_no}">Remove</button>
      </div>
    `)
    .join("");
}

function renderKeepers() {
  const container = $("#keepers");
  if (!state.keepers.length) {
    container.innerHTML = emptyState("No manual keepers added.");
    return;
  }
  container.innerHTML = state.keepers
    .map((keeper) => {
      const cost = [keeper.round ? `Round ${keeper.round}` : "", keeper.pick_no ? `Pick ${keeper.pick_no}` : ""]
        .filter(Boolean)
        .join(" · ");
      return `
        <div class="compact-row">
          <div>
            <strong>${escapeHtml(keeper.player?.name || keeper.player?.full_name || keeper.player_id)}</strong>
            <span>${escapeHtml(keeper.team_name)}${cost ? ` · ${escapeHtml(cost)}` : ""}</span>
          </div>
          <button class="text-button" data-remove-keeper="${keeper.player_id}" data-team="${escapeHtml(keeper.team_name)}">Remove</button>
        </div>
      `;
    })
    .join("");
}

function renderWaivers() {
  const container = $("#waiver-groups");
  const positions = Object.keys(state.waiverGroups);
  if (!positions.length) {
    container.innerHTML = emptyState("No waiver groups available.");
    return;
  }
  container.innerHTML = positions
    .map((position) => `
      <section class="waiver-group">
        <h3>${position}</h3>
        ${state.waiverGroups[position].map((item) => waiverCard(item)).join("")}
      </section>
    `)
    .join("");
}

function waiverCard(item) {
  const player = item.player;
  const why = item.why || [];
  return `
    <article class="waiver-card">
      <div class="player-title">
        <strong>${escapeHtml(player.name || player.full_name)}</strong>
        <span class="tag position">${escapeHtml(player.position || "UNK")} · ${escapeHtml(player.team || "")}</span>
      </div>
      ${item.trend_count !== undefined ? `<p>${escapeHtml(`Sleeper trend count: ${item.trend_count}`)}</p>` : ""}
      ${why.filter(Boolean).map((reason) => `<p>${escapeHtml(reason)}</p>`).join("")}
      ${item.consensus?.label ? `<p>${escapeHtml(`Consensus label: ${item.consensus.label}`)}</p>` : ""}
    </article>
  `;
}

function emptyState(text) {
  return `<div class="compact-row"><span>${escapeHtml(text)}</span></div>`;
}

function findPlayerByName(name) {
  const normalized = normalize(name);
  return state.players.find((player) => normalize(player.name || player.full_name) === normalized)
    || state.players.find((player) => normalize(player.name || player.full_name).includes(normalized));
}

function normalize(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

async function refreshDraft() {
  const [picks, keepers, draft] = await Promise.all([
    api("/api/draft/picks"),
    api("/api/keepers"),
    api(`/api/draft/recommendations?${draftQueryString()}`),
  ]);
  state.picks = picks.picks;
  state.keepers = keepers.keepers;
  state.recommendations = draft.recommendations;
  state.currentPick = draft.current_pick;
  renderStatus();
  renderRecommendations();
  renderPicks();
  renderKeepers();
}

async function refreshWaivers() {
  try {
    const waivers = await api("/api/integrations/sleeper/trending/enriched?limit=25");
    state.waiverGroups = waivers.groups;
  } catch (error) {
    const waivers = await api("/api/waivers/rising?positions=QB,RB,WR,TE,DEF,K");
    state.waiverGroups = waivers.groups;
  }
  renderWaivers();
}

async function refreshPlayers() {
  const query = new URLSearchParams();
  const position = $("#draft-position-filter")?.value;
  const search = $("#draft-search-filter")?.value.trim();
  if (position) query.set("position", position);
  if (search) query.set("search", search);
  query.set("active", "1");
  const players = await api(`/api/players?${query.toString()}`);
  state.players = players.players;
  state.playerSource = players.source;
  renderPlayerOptions();
}

function draftQueryString() {
  const query = new URLSearchParams();
  query.set("limit", "12");
  const position = $("#draft-position-filter")?.value;
  const search = $("#draft-search-filter")?.value.trim();
  if (position) query.set("position", position);
  if (search) query.set("search", search);
  query.set("hide_drafted", $("#hide-drafted-filter")?.checked ? "1" : "0");
  query.set("hide_keepers", $("#hide-keepers-filter")?.checked ? "1" : "0");
  return query.toString();
}

function setActiveTab(tab) {
  $$(".nav-tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${tab}`));
}

function addMessage(role, text) {
  const log = $("#chat-log");
  log.insertAdjacentHTML(
    "beforeend",
    `<div class="message ${role}"><strong>${role === "user" ? "You" : "Assistant"}</strong>${escapeHtml(text)}</div>`
  );
  log.scrollTop = log.scrollHeight;
}

async function submitChat(message) {
  addMessage("user", message);
  const response = await api("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  addMessage("assistant", response.answer);
}

function toast(text) {
  const node = $("#toast");
  node.textContent = text;
  node.classList.add("visible");
  window.clearTimeout(toast.timeout);
  toast.timeout = window.setTimeout(() => node.classList.remove("visible"), 3200);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("button");
  if (!target) return;

  if (target.matches(".nav-tab")) {
    setActiveTab(target.dataset.tab);
    return;
  }

  if (target.matches(".prompt-button")) {
    $("#chat-input").value = target.textContent;
    $("#chat-form").requestSubmit();
    return;
  }

  if (target.id === "refresh-draft") {
    await refreshDraft();
    toast("Draft board refreshed.");
    return;
  }

  if (target.id === "refresh-waivers") {
    await refreshWaivers();
    toast("Waiver watchlist refreshed.");
    return;
  }

  if (target.id === "import-sleeper-players") {
    target.disabled = true;
    target.textContent = "Importing...";
    try {
      const result = await api("/api/integrations/sleeper/players/import", { method: "POST" });
      await refreshPlayers();
      await refreshDraft();
      toast(`Imported ${result.imported_count} Sleeper players.`);
    } finally {
      target.disabled = false;
      target.textContent = "Import Sleeper Players";
    }
    return;
  }

  if (target.id === "refresh-consensus") {
    const result = await api(`/api/players/consensus?limit=25&current_pick=${encodeURIComponent(state.currentPick || 1)}`);
    await refreshDraft();
    toast(`Consensus refreshed for ${result.players.length} players.`);
    return;
  }

  if (target.id === "clear-picks") {
    await api("/api/draft/picks", { method: "DELETE" });
    await refreshDraft();
    toast("Draft picks cleared.");
    return;
  }

  if (target.id === "clear-keepers") {
    await api("/api/keepers", { method: "DELETE" });
    await refreshDraft();
    toast("Keepers cleared.");
    return;
  }

  const draftMe = target.dataset.draftMe;
  const draftTaken = target.dataset.draftTaken;
  if (draftMe || draftTaken) {
    await api("/api/draft/picks", {
      method: "POST",
      body: JSON.stringify({
        player_id: draftMe || draftTaken,
        manager: draftMe ? "me" : "opponent",
      }),
    });
    await refreshDraft();
    toast(draftMe ? "Player added to your roster." : "Player marked as taken.");
    return;
  }

  if (target.dataset.removePick) {
    await api(`/api/draft/picks?pick_no=${encodeURIComponent(target.dataset.removePick)}`, { method: "DELETE" });
    await refreshDraft();
    return;
  }

  if (target.dataset.removeKeeper) {
    await api(`/api/keepers?player_id=${encodeURIComponent(target.dataset.removeKeeper)}&team_name=${encodeURIComponent(target.dataset.team)}`, { method: "DELETE" });
    await refreshDraft();
  }
});

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.settings = await api("/api/league/settings", {
    method: "POST",
    body: JSON.stringify({
      teams: Number($("#settings-teams").value),
      draft_slot: Number($("#settings-slot").value),
      scoring: $("#settings-scoring").value,
    }),
  });
  await refreshDraft();
  toast("Settings saved.");
});

$("#keeper-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const player = findPlayerByName($("#keeper-player").value);
  if (!player) {
    toast("Choose a player from the current player pool.");
    return;
  }
  await api("/api/keepers", {
    method: "POST",
    body: JSON.stringify({
      player_id: player.id,
      team_name: $("#keeper-team").value,
      round: $("#keeper-round").value || null,
      pick_no: $("#keeper-pick").value || null,
    }),
  });
  event.target.reset();
  await refreshDraft();
  await refreshWaivers();
  toast("Keeper added.");
});

$("#pick-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const player = findPlayerByName($("#pick-player").value);
  if (!player) {
    toast("Choose a player from the current player pool.");
    return;
  }
  await api("/api/draft/picks", {
    method: "POST",
    body: JSON.stringify({
      player_id: player.id,
      pick_no: $("#pick-number").value || null,
      manager: $("#pick-manager").value,
    }),
  });
  event.target.reset();
  await refreshDraft();
  await refreshWaivers();
  toast("Draft pick added.");
});

$("#sleeper-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const leagueId = $("#sleeper-league").value.trim();
  if (!leagueId) {
    toast("Enter a Sleeper league ID.");
    return;
  }
  const result = await api("/api/integrations/sleeper/import", {
    method: "POST",
    body: JSON.stringify({ league_id: leagueId }),
  });
  state.settings = result.imported.league_settings;
  renderStatus();
  await refreshDraft();
  toast(`Imported ${result.snapshot.name || "Sleeper league"}.`);
});

$("#rankings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  let parsed;
  try {
    parsed = JSON.parse($("#rankings-json").value);
  } catch (error) {
    toast("Rankings JSON is not valid.");
    return;
  }
  const rows = Array.isArray(parsed) ? parsed : parsed.rows;
  if (!Array.isArray(rows)) {
    toast("Rankings JSON must be an array or an object with rows.");
    return;
  }
  const result = await api("/api/rankings/import/csv", {
    method: "POST",
    body: JSON.stringify({
      source_name: $("#rankings-source").value,
      rows,
    }),
  });
  await refreshPlayers();
  await refreshDraft();
  toast(`Imported ${result.imported_count} ${result.source_name} rankings.`);
});

["draft-position-filter", "hide-drafted-filter", "hide-keepers-filter"].forEach((id) => {
  $(`#${id}`).addEventListener("change", async () => {
    await refreshPlayers();
    await refreshDraft();
  });
});

$("#draft-search-filter").addEventListener("input", debounce(async () => {
  await refreshPlayers();
  await refreshDraft();
}, 250));

function debounce(callback, wait) {
  let timeout;
  return (...args) => {
    window.clearTimeout(timeout);
    timeout = window.setTimeout(() => callback(...args), wait);
  };
}

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  try {
    await submitChat(message);
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

loadAll().then(() => {
  addMessage("assistant", "Ready. Ask me about the draft board, waiver risers, keepers, or weekly matchups.");
}).catch((error) => {
  toast(error.message);
});
