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

async function openPickSheet(pickNo) {
  const dialog = $("#pick-sheet");
  if (!dialog || !state.leagueId) return;
  $("#pick-sheet-title").textContent = `Pick ${pickNo} · ${state.currentPickTeam?.manager_name || "On the clock"}`;
  state.pickSheetPosition = "";
  await renderPickSheetList(pickNo);
  dialog.showModal();
}

async function renderPickSheetList(pickNo) {
  const list = $("#pick-sheet-list");
  const filters = $("#pick-sheet-filters");
  if (!list) return;
  list.innerHTML = emptyState("Loading...");
  const query = new URLSearchParams({ league_id: state.leagueId, pick_no: String(pickNo), limit: "12" });
  if (state.pickSheetPosition) query.set("position", state.pickSheetPosition);
  const payload = await api(`/api/draft/recommendations?${query}`);
  const recs = payload.recommendations || [];
  if (filters) {
    filters.innerHTML = ["", "QB", "RB", "WR", "TE"]
      .map(
        (pos) =>
          `<button type="button" class="ghost-button small-button" data-pick-filter="${pos}">${pos || "All"}</button>`,
      )
      .join("");
  }
  if (!recs.length) {
    list.innerHTML = emptyState("No players available for this pick.");
    return;
  }
  list.innerHTML = recs
    .map((item) => {
      const player = item.player;
      const id = player.internal_player_id || player.id;
      const starred = state.favoriteIds.has(id);
      return `<article class="pick-sheet-row"><div><strong>${escapeHtml(player.full_name)}</strong>
        <span class="tag position">${escapeHtml(player.position)} · ${escapeHtml(player.team || "")}</span>
        <p>Score ${escapeHtml(item.score)} · ${escapeHtml(item.fit)}</p></div>
        <div class="pick-sheet-actions">
        <button type="button" class="primary-button small-button" data-pick-sheet-draft="${escapeHtml(id)}">Draft</button>
        <button type="button" class="ghost-button small-button" data-toggle-favorite="${escapeHtml(id)}">${starred ? "★" : "☆"}</button>
        </div></article>`;
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
  if (state.leagueId) await Promise.all([refreshFavorites(), refreshPreferences()]);
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
    if ($("#pick-sheet")?.open) await renderPickSheetList(state.currentPick);
    return;
  }
  if (target.dataset.pickFilter !== undefined) {
    state.pickSheetPosition = target.dataset.pickFilter;
    await renderPickSheetList(state.currentPick);
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
