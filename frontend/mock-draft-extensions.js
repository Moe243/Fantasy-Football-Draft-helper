const PICK_SHEET_POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "DEF", "K"];

async function refreshFavorites() {
  if (!state.leagueId) return;
  const payload = await api(`/api/user/favorites?league_id=${encodeURIComponent(state.leagueId)}`);
  state.favoriteIds = new Set((payload.favorites || []).map((row) => row.player_id));
  const container = $("#favorites-list");
  if (!container) return;
  if (!payload.favorites?.length) {
    container.innerHTML = emptyState("Star players from the pick sheet to add favorites.");
    return;
  }
  container.innerHTML = payload.favorites
    .map(
      (row) => `<div class="compact-row"><span>${escapeHtml(row.full_name || row.player_id)}</span>
      <button class="text-button" data-remove-favorite="${escapeHtml(row.player_id)}">Remove</button></div>`,
    )
    .join("");
}

async function refreshDataSources() {
  const payload = await api("/api/setup/data-sources");
  const container = $("#data-sources-status");
  if (!container) return;
  container.innerHTML = Object.entries(payload.keys || {})
    .map(([name, ok]) => `<div class="compact-row"><span>${escapeHtml(name)}</span><strong>${ok ? "Configured" : "Missing"}</strong></div>`)
    .join("");
}

async function refreshPreferences() {
  if (!state.leagueId) return;
  const prefs = await api(`/api/user/draft-preferences?league_id=${encodeURIComponent(state.leagueId)}`);
  if ($("#pref-reach-bias")) $("#pref-reach-bias").value = prefs.reach_bias ?? 0;
  if ($("#pref-value-bias")) $("#pref-value-bias").value = prefs.value_bias ?? 0;
}

async function refreshManagerNamesTable() {
  const table = $("#manager-names-table");
  if (!table || !state.leagueId) return;
  const payload = await api(`/api/league/managers?league_id=${encodeURIComponent(state.leagueId)}`);
  const managers = payload.managers || [];
  if (!managers.length) {
    table.innerHTML = emptyState("Import your Sleeper league to edit manager and team names.");
    return;
  }
  table.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Draft Slot</th>
          <th>Sleeper Username</th>
          <th>Custom Manager Name</th>
          <th>Custom Team Name</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${managers
          .map((row) => {
            const slot = row.draft_slot ?? "—";
            return `<tr data-roster-id="${escapeHtml(row.roster_id)}">
              <td>${escapeHtml(slot)}</td>
              <td>${escapeHtml(row.sleeper_display_name || row.display_name || "")}</td>
              <td><input class="manager-local-display" value="${escapeHtml(row.custom_manager_name || row.local_display_name || "")}" /></td>
              <td><input class="manager-local-team" value="${escapeHtml(row.custom_team_name || row.local_team_name || "")}" /></td>
              <td class="button-row">
                <button type="button" class="ghost-button small-button" data-save-manager="${escapeHtml(row.roster_id)}">Save</button>
                <button type="button" class="text-button small-button" data-reset-manager="${escapeHtml(row.roster_id)}">Reset</button>
              </td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>`;
}

function historyLine(history, season) {
  const entry = history?.[String(season)];
  if (!entry || (entry.rank == null && entry.fantasy_points == null)) {
    return `No ${season} history imported`;
  }
  const rank = entry.rank != null ? `Rank ${entry.rank}` : "Rank —";
  const pts = entry.fantasy_points != null ? `${Number(entry.fantasy_points).toFixed(1)} pts` : "— pts";
  return `${rank} / ${pts}`;
}

function propsLine(props) {
  if (!props?.length) return "No 2026 props imported";
  return props
    .slice(0, 4)
    .map((p) => `${String(p.market || "").replace(/_/g, " ")} ${p.line ?? ""}`.trim())
    .filter(Boolean)
    .join("; ");
}

function signalsHtml(signals) {
  if (!signals) return "";
  const rows = Object.entries(signals)
    .map(([key, value]) => `<div><span>${escapeHtml(key.replace(/_/g, " "))}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
  return `<div class="signal-grid">${rows}</div>`;
}

async function openPickSheet(pickNo) {
  const dialog = $("#pick-sheet");
  if (!dialog || !state.leagueId) return;
  state.pickSheetPickNo = pickNo;
  $("#pick-sheet-title").textContent = `Pick ${pickNo} · ${state.currentPickTeam?.manager_name || "On the clock"}`;
  if (!state.pickSheetPosition) state.pickSheetPosition = "ALL";
  await renderPickSheetList(pickNo);
  dialog.showModal();
}

async function renderPickSheetList(pickNo) {
  const list = $("#pick-sheet-list");
  const filters = $("#pick-sheet-filters");
  if (!list) return;
  list.innerHTML = emptyState("Loading...");
  const query = new URLSearchParams({
    league_id: state.leagueId,
    pick_no: String(pickNo),
    limit: "30",
  });
  if (state.pickSheetPosition && state.pickSheetPosition !== "ALL") {
    query.set("position", state.pickSheetPosition);
  }
  const payload = await api(`/api/draft/recommendations?${query}`);
  const recs = payload.recommendations || [];
  if (filters) {
    filters.innerHTML = PICK_SHEET_POSITIONS.map((pos) => {
      const active = state.pickSheetPosition === pos ? " active" : "";
      return `<button type="button" class="ghost-button small-button pick-filter${active}" data-pick-filter="${pos}">${pos}</button>`;
    }).join("");
  }
  if (!recs.length) {
    list.innerHTML = emptyState("No players available for this filter.");
    return;
  }
  list.innerHTML = recs
    .map((item) => {
      const player = item.player;
      const id = player.internal_player_id || player.id;
      const starred = state.favoriteIds.has(id);
      const reasons = (item.reasons || []).slice(0, 3);
      const topReason = reasons[0] || "Ranking based on consensus and roster fit.";
      return `<article class="pick-sheet-row">
        <div class="pick-sheet-main">
          <div class="pick-sheet-title-row">
            <strong>${escapeHtml(player.full_name)}</strong>
            <span class="tag position">${escapeHtml(player.position)} · ${escapeHtml(player.team || "")}</span>
          </div>
          <p class="pick-sheet-meta">Score ${escapeHtml(item.score)} · ${escapeHtml(item.fit)} · ${escapeHtml(topReason)}</p>
          <p class="pick-sheet-meta">2025: ${escapeHtml(historyLine(item.history, 2025))}</p>
          <p class="pick-sheet-meta">2024: ${escapeHtml(historyLine(item.history, 2024))}</p>
          <p class="pick-sheet-meta">2026 Props: ${escapeHtml(propsLine(item.props_2026))}</p>
          <p class="pick-sheet-meta">Outlook: ${escapeHtml(item.outlook || "No outlook generated yet.")}</p>
          ${item.market_signal ? `<p class="pick-sheet-meta">${escapeHtml(item.market_signal)}</p>` : ""}
          <details class="pick-sheet-why">
            <summary>Why this rank?</summary>
            <ul>${reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
            ${signalsHtml(item.signals)}
          </details>
        </div>
        <div class="pick-sheet-actions">
          <button type="button" class="primary-button small-button" data-pick-sheet-draft="${escapeHtml(id)}">Draft</button>
          <button type="button" class="ghost-button small-button" data-toggle-favorite="${escapeHtml(id)}">${starred ? "★" : "☆"}</button>
        </div>
      </article>`;
    })
    .join("");
}

function closePickSheet() {
  $("#pick-sheet")?.close?.();
}

const _loadAll = loadAll;
loadAll = async function loadAllWithMock() {
  await _loadAll();
  await refreshDataSources();
  if (state.leagueId) {
    await Promise.all([refreshFavorites(), refreshPreferences(), refreshManagerNamesTable()]);
  }
};

const _refreshLeagueManagers = refreshLeagueManagers;
refreshLeagueManagers = async function refreshLeagueManagersWithNames() {
  await _refreshLeagueManagers();
  await refreshManagerNamesTable();
};

document.addEventListener("click", async (event) => {
  const cell = event.target.closest("[data-pick-cell]");
  if (cell && state.draftMode === "mock" && !state.mockDraft?.is_complete && !event.target.closest("button")) {
    await openPickSheet(Number(cell.dataset.pickCell));
    return;
  }
  const target = event.target.closest("button");
  if (!target) return;
  if (target.id === "refresh-data-sources") {
    await refreshDataSources();
    toast("Data sources refreshed.");
    return;
  }
  if (target.id === "import-sleeper-projections") {
    await api("/api/integrations/sleeper/projections/import", { method: "POST", body: "{}" });
    await refreshDataSources();
    toast("Sleeper projections imported.");
    return;
  }
  if (target.id === "import-odds") {
    await api("/api/integrations/odds/import", { method: "POST", body: "{}" });
    await refreshDataSources();
    toast("NFL odds imported.");
    return;
  }
  if (target.dataset.saveManager) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const row = target.closest("tr");
    await api("/api/league/managers/update", {
      method: "POST",
      body: JSON.stringify({
        league_id: leagueId,
        roster_id: Number(target.dataset.saveManager),
        local_display_name: row.querySelector(".manager-local-display")?.value || null,
        local_team_name: row.querySelector(".manager-local-team")?.value || null,
      }),
    });
    await Promise.all([refreshLeagueManagers(), refreshDraftState()]);
    toast("Manager names saved.");
    return;
  }
  if (target.dataset.resetManager) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api("/api/league/managers/reset", {
      method: "POST",
      body: JSON.stringify({
        league_id: leagueId,
        roster_id: Number(target.dataset.resetManager),
      }),
    });
    await Promise.all([refreshLeagueManagers(), refreshDraftState()]);
    toast("Manager names reset.");
    return;
  }
  if (target.id === "calc-user-tendencies") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const result = await api("/api/user/tendencies/calculate", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId }),
    });
    toast(`Calculated tendencies from ${result.picks_analyzed} historical picks.`);
    return;
  }
  if (target.dataset.removeFavorite) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api(
      `/api/user/favorites?league_id=${encodeURIComponent(leagueId)}&player_id=${encodeURIComponent(target.dataset.removeFavorite)}`,
      { method: "DELETE" },
    );
    await refreshFavorites();
    return;
  }
  if (target.dataset.pickSheetDraft) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    applyDraftState(
      await api("/api/draft/pick", {
        method: "POST",
        body: JSON.stringify({
          league_id: leagueId,
          player_id: target.dataset.pickSheetDraft,
          pick_no: state.pickSheetPickNo || state.currentPick,
          practice_draft_id: state.practiceStatus?.practice?.id || null,
        }),
      }),
    );
    closePickSheet();
    toast("Pick saved.");
    return;
  }
  if (target.dataset.toggleFavorite) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const playerId = target.dataset.toggleFavorite;
    if (state.favoriteIds.has(playerId)) {
      await api(
        `/api/user/favorites?league_id=${encodeURIComponent(leagueId)}&player_id=${encodeURIComponent(playerId)}`,
        { method: "DELETE" },
      );
    } else {
      await api("/api/user/favorites", {
        method: "POST",
        body: JSON.stringify({ league_id: leagueId, player_id: playerId }),
      });
    }
    await refreshFavorites();
    if ($("#pick-sheet")?.open) await renderPickSheetList(state.pickSheetPickNo || state.currentPick);
    return;
  }
  if (target.dataset.pickFilter !== undefined) {
    state.pickSheetPosition = target.dataset.pickFilter;
    await renderPickSheetList(state.pickSheetPickNo || state.currentPick);
    return;
  }
  if (target.id === "pick-sheet-close") {
    closePickSheet();
  }
});

if ($("#preferences-form")) {
  $("#preferences-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api("/api/user/draft-preferences", {
      method: "POST",
      body: JSON.stringify({
        league_id: leagueId,
        reach_bias: Number($("#pref-reach-bias").value),
        value_bias: Number($("#pref-value-bias").value),
      }),
    });
    toast("Draft preferences saved.");
  });
}

const practiceStartBtn = document.getElementById("practice-start");
if (practiceStartBtn) {
  practiceStartBtn.addEventListener(
    "click",
    () => {
      window.setTimeout(() => setActiveTab("practice"), 50);
    },
    true,
  );
}
