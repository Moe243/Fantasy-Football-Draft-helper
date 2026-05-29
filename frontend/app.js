const state = {
  players: [],
  settings: null,
  keepers: [],
  picks: [],
  recommendations: [],
  waiverGroups: {},
  playerSource: "sample",
  currentPick: 1,
  currentPickTeam: null,
  isMyPick: false,
  leagueId: window.localStorage.getItem("sleeperLeagueId") || "",
  setupStatus: null,
  managers: [],
  draftMapping: [],
  draftBoard: null,
  draftState: null,
  bestAvailable: [],
  myPicks: [],
  likelyAvailable: [],
  rosterNeeds: [],
  playersSearch: { players: [], total: 0, limit: 50, offset: 0 },
  selectedPlayer: null,
  practiceStatus: null,
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
  if ($("#sleeper-league")) $("#sleeper-league").value = state.leagueId;
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
  await Promise.all([refreshWaivers(), refreshSetupStatus(), refreshPlayersSearch()]);
  if (state.leagueId) {
    await Promise.all([refreshLeagueManagers(), refreshDraftState()]);
  }
}

function renderAll() {
  renderStatus();
  renderPlayerOptions();
  renderRecommendations();
  renderPicks();
  renderKeepers();
  renderWaivers();
  renderDraftRoomStatus();
  renderDraftBoard();
  renderMyUpcomingPicks();
  renderRosterNeeds();
  renderPlayersTable();
  renderPlayerDetail();
  renderMyTeamSelect();
  renderDraftOrderMapping();
  renderImportStatus();
  renderPracticeStatus();
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
    .map((player) => `<option value="${escapeHtml(player.name || player.full_name)}">${escapeHtml(`${player.position || "UNK"} · ${player.team || ""}`)}</option>`)
    .join("");
}

function renderRecommendations() {
  const container = $("#recommendations");
  if (!state.recommendations.length) {
    container.innerHTML = emptyState("No best available players yet. Import your Sleeper league and player data, then refresh the draft room.");
    return;
  }
  container.innerHTML = state.recommendations
    .map((item) => {
      const player = item.player;
      const playerName = player.name || player.full_name;
      const playerId = player.id || player.internal_player_id;
      const risk = player.injury_status && !["Healthy", "Active"].includes(player.injury_status)
        ? `<span class="tag risk">${escapeHtml(player.injury_status)}</span>`
        : "";
      return `
        <article class="recommendation-card">
          <div>
            <div class="player-title">
              <strong>${escapeHtml(playerName)}</strong>
              <span class="tag position">${escapeHtml(player.position || "UNK")} · ${escapeHtml(player.team || "")}</span>
              <span class="tag fit">${escapeHtml(item.fit)}</span>
              ${risk}
            </div>
            ${renderConsensusGrid(item)}
            <ul class="reason-list">
              ${(item.reasons || []).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
            </ul>
            <div class="card-actions">
              <button class="primary-button small-button" data-draft-player="${escapeHtml(playerId)}">Draft</button>
              <button class="small-button" data-player-detail="${escapeHtml(playerId)}">Details</button>
            </div>
          </div>
          <div class="score-box">
            <span>Score</span>
            <strong>${escapeHtml(item.score)}</strong>
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
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return String(value);
}

function renderPicks() {
  const container = $("#draft-picks");
  $("#pick-number").placeholder = state.leagueId ? `Current (${state.currentPick || 1})` : String((state.picks.at(-1)?.pick_no || 0) + 1);
  if (!state.picks.length) {
    container.innerHTML = emptyState("No manual draft picks marked yet.");
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
          <button class="text-button" data-remove-keeper="${escapeHtml(keeper.player_id)}" data-team="${escapeHtml(keeper.team_name)}">Remove</button>
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
        <h3>${escapeHtml(position)}</h3>
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

function renderDraftBoard(boardData = state.draftBoard, selector = "#league-draft-board") {
  const container = $(selector);
  if (!container) return;
  container.innerHTML = draftBoardHtml(boardData);
}

function renderDraftRoomStatus() {
  const container = $("#draft-room-status");
  if (!container) return;
  if (!state.leagueId) {
    container.innerHTML = `<span class="metric-chip">No league</span>`;
    return;
  }
  const team = state.currentPickTeam;
  const teamName = team?.manager_name || "Unknown team";
  const label = state.isMyPick ? "Your pick" : "On the clock";
  container.innerHTML = `
    <div class="current-pick-banner${state.isMyPick ? " mine" : ""}">
      <span>${escapeHtml(label)}</span>
      <strong>Pick ${escapeHtml(state.currentPick || 1)}</strong>
      <small>${escapeHtml(teamName)}</small>
    </div>
  `;
}

function draftBoardHtml(boardData) {
  if (!state.leagueId) {
    return emptyState("Enter a Sleeper league ID in Setup to build your league draft board.");
  }
  if (!boardData?.board?.length) {
    return emptyState("No imported draft board yet. Import your Sleeper league from Setup.");
  }
  const teamCount = Math.max(1, boardData.draft_order?.length || boardData.managers?.length || state.settings?.teams || 10);
  const headers = (boardData.draft_order?.length ? boardData.draft_order : boardData.managers || [])
    .slice(0, teamCount)
    .map((manager, index) => manager.manager_name || manager.team_name || manager.display_name || `Slot ${index + 1}`);
  while (headers.length < teamCount) headers.push(`Slot ${headers.length + 1}`);
  const headerRow = `
    <div class="draft-board-row">
      <div class="draft-board-cell header">Round</div>
      ${headers.map((name) => `<div class="draft-board-cell header">${escapeHtml(name)}</div>`).join("")}
    </div>
  `;
  const rows = boardData.board.map((round) => `
    <div class="draft-board-row">
      <div class="draft-board-cell round-label">Round ${round.round}</div>
      ${(round.picks || []).map((pick) => draftCell(pick)).join("")}
    </div>
  `).join("");
  return `<div class="draft-board-table" style="--team-count: ${teamCount}">${headerRow}${rows}</div>`;
}

function draftCell(pick) {
  const player = pick.player;
  const classes = ["draft-board-cell"];
  if (pick.is_mine) classes.push("mine");
  if (pick.is_current_pick) classes.push("current");
  if (pick.is_my_current_pick) classes.push("my-current");
  if (pick.is_keeper) classes.push("keeper");
  const playerLabel = player
    ? `<strong>${escapeHtml(player.name || player.full_name)}</strong><span>${escapeHtml(player.position || "")}${player.team ? ` · ${escapeHtml(player.team)}` : ""}</span><small>${escapeHtml(pick.manager_name || "")}</small>`
    : `<strong>Pick ${escapeHtml(pick.pick_no)}</strong><span>${escapeHtml(pick.manager_name || "Open")}</span>`;
  const keeper = pick.is_keeper ? `<span class="tag fit">Keeper</span>` : "";
  const practice = pick.practice_source ? `<span class="tag position">${escapeHtml(pick.practice_source)}</span>` : "";
  const traded = pick.is_traded ? `<span class="tag traded-tag">Traded</span>` : "";
  const current = pick.is_current_pick ? `<span class="tag current-tag">${pick.is_mine ? "My pick" : "Current"}</span>` : "";
  const remove = player && !pick.is_keeper ? `<button class="text-button remove-pick-button" data-remove-board-pick="${escapeHtml(pick.pick_no)}">Remove</button>` : "";
  return `
    <div class="${classes.join(" ")}">
      <span class="pick-meta">Pick ${escapeHtml(pick.pick_no)} · Slot ${escapeHtml(pick.draft_slot)}</span>
      ${playerLabel}
      <div class="pick-tags">${current}${keeper}${traded}${practice}${remove}</div>
    </div>
  `;
}

function renderMyUpcomingPicks() {
  const container = $("#my-upcoming-picks");
  if (!container) return;
  if (!state.leagueId) {
    container.innerHTML = emptyState("Import your Sleeper league to see your upcoming picks.");
    return;
  }
  const picks = state.myPicks || state.draftBoard?.my_picks || [];
  if (!picks.length) {
    container.innerHTML = emptyState("Select My Team in Setup to highlight your picks.");
    return;
  }
  const upcoming = picks.filter((pick) => Number(pick.pick_no) >= Number(state.currentPick || 1)).slice(0, 8);
  container.innerHTML = upcoming.map((pick) => {
    const names = (pick.likely_available || [])
      .map((item) => item.player?.full_name || item.player?.name)
      .filter(Boolean)
      .join(", ");
    return `
      <article class="upcoming-pick-card">
        <strong>Round ${escapeHtml(pick.round)}, Pick ${escapeHtml(pick.pick_no)}</strong>
        <span>Draft slot ${escapeHtml(pick.draft_slot)} · ${escapeHtml(pick.manager_name || "Your team")}</span>
        <p>${names ? `Likely available: ${escapeHtml(names)}` : "Likely available players will appear after rankings are imported."}</p>
      </article>
    `;
  }).join("");
}

function renderRosterNeeds() {
  const container = $("#roster-needs");
  if (!container) return;
  const needs = state.rosterNeeds || [];
  if (!needs.length) {
    container.innerHTML = emptyState("Select My Team and start drafting to track roster needs.");
    return;
  }
  container.innerHTML = needs.map((need) => `
    <div class="need-row${need.remaining > 0 ? "" : " filled"}">
      <strong>${escapeHtml(need.position)}</strong>
      <span>${escapeHtml(need.current)} / ${escapeHtml(need.target)}</span>
      <em>${need.remaining > 0 ? `${escapeHtml(need.remaining)} needed` : "Filled"}</em>
    </div>
  `).join("");
}

function renderPlayersTable() {
  const container = $("#players-table");
  if (!container) return;
  const players = state.playersSearch.players || [];
  if (!players.length) {
    container.innerHTML = emptyState("No players match those filters.");
    return;
  }
  container.innerHTML = `
    <div class="players-row header">
      <span>Name</span><span>Pos</span><span>Team</span><span>No.</span><span>Age</span>
      <span>Injury</span><span>Rank</span><span>Proj</span><span>Sources</span><span></span>
    </div>
    ${players.map((player) => `
      <div class="players-row">
        <strong>${escapeHtml(player.full_name)}</strong>
        <span>${escapeHtml(player.position || "")}</span>
        <span>${escapeHtml(player.team || "")}</span>
        <span>${escapeHtml(player.jersey_number || "")}</span>
        <span>${escapeHtml(player.age || "")}</span>
        <span>${escapeHtml(player.injury_status || "")}</span>
        <span>${escapeHtml(formatMetric(player.consensus_rank))}</span>
        <span>${escapeHtml(formatMetric(player.projected_points_avg))}</span>
        <span>${escapeHtml(player.source_count || 0)}</span>
        <button class="small-button" data-player-detail="${escapeHtml(player.internal_player_id)}">View</button>
      </div>
    `).join("")}
  `;
}

function renderPlayerDetail() {
  const container = $("#player-detail");
  if (!container) return;
  const detail = state.selectedPlayer;
  if (!detail) {
    container.innerHTML = "Select a player to view details.";
    return;
  }
  const player = detail.player;
  container.innerHTML = `
    <article class="player-detail-panel">
      <div class="player-title">
        <strong>${escapeHtml(player.full_name)}</strong>
        <span class="tag position">${escapeHtml(player.position || "UNK")} · ${escapeHtml(player.team || "")}</span>
      </div>
      <div class="detail-grid">
        <section class="detail-section">
          <h4>Profile</h4>
          ${detailRow("Number", player.jersey_number)}
          ${detailRow("Age", player.age)}
          ${detailRow("Height / Weight", [player.height, player.weight].filter(Boolean).join(" / "))}
          ${detailRow("Years Exp", player.years_exp)}
          ${detailRow("College", player.college)}
          ${detailRow("Status", player.injury_status || player.status)}
        </section>
        <section class="detail-section">
          <h4>Consensus</h4>
          ${detailRow("Rank", detail.consensus?.consensus_rank)}
          ${detailRow("Label", detail.consensus?.label)}
          ${detailRow("Projected Points", detail.consensus?.projected_points_avg)}
          ${detailRow("Source Count", detail.consensus?.source_count)}
          ${detailRow("Spread", detail.consensus?.rank_spread)}
        </section>
      </div>
      <section class="detail-section">
        <h4>Rankings by Source</h4>
        ${rankingsTable(detail.rankings || {})}
      </section>
      <section class="detail-section">
        <h4>Stats History</h4>
        ${statsTable(detail.stats || {}, "actual")}
      </section>
      <section class="detail-section">
        <h4>Projections</h4>
        ${statsTable(detail.stats || {}, "projected")}
      </section>
      <section class="detail-section">
        <h4>Props</h4>
        ${propsTable(detail.props || [])}
      </section>
      <section class="detail-section">
        <h4>Notes</h4>
        ${(detail.notes || []).length ? `<ul class="reason-list">${detail.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : emptyState("No notes yet.")}
      </section>
      <section class="detail-section">
        <h4>News</h4>
        ${newsList(detail.news || [])}
      </section>
    </article>
  `;
}

function detailRow(label, value) {
  return `<div class="detail-row two-column"><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatMetric(value))}</strong></div>`;
}

function rankingsTable(rankings) {
  const rows = Object.entries(rankings);
  if (!rows.length) return emptyState("No source rankings imported for this player.");
  return `
    <div class="detail-table">
      <div class="detail-row"><strong>Source</strong><strong>Rank</strong><strong>Pos</strong><strong>ADP</strong><strong>Proj</strong><strong>Tier</strong></div>
      ${rows.map(([source, row]) => `
        <div class="detail-row">
          <span>${escapeHtml(source)}</span>
          <span>${escapeHtml(formatMetric(row.overall_rank))}</span>
          <span>${escapeHtml(row.position_rank || "")}</span>
          <span>${escapeHtml(formatMetric(row.adp))}</span>
          <span>${escapeHtml(formatMetric(row.projected_points))}</span>
          <span>${escapeHtml(row.tier || "")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function statsTable(stats, type) {
  const rows = stats[type] || [];
  if (!rows.length) return emptyState(`No ${type} stats imported.`);
  return `
    <div class="detail-table">
      <div class="detail-row"><strong>Season</strong><strong>Week</strong><strong>Rec</strong><strong>Rush</strong><strong>Pass</strong><strong>FP</strong></div>
      ${rows.slice(0, 12).map((row) => `
        <div class="detail-row">
          <span>${escapeHtml(row.season || "")}</span>
          <span>${escapeHtml(row.week || "")}</span>
          <span>${escapeHtml(statPair(row.receptions, row.receiving_yards))}</span>
          <span>${escapeHtml(statPair(row.rushing_attempts, row.rushing_yards))}</span>
          <span>${escapeHtml(formatMetric(row.passing_yards))}</span>
          <span>${escapeHtml(formatMetric(row.fantasy_points))}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function statPair(a, b) {
  if (a === null && b === null) return "";
  return `${formatMetric(a)}/${formatMetric(b)}`;
}

function propsTable(props) {
  if (!props.length) return emptyState("No props imported for this player.");
  return `
    <div class="detail-table">
      <div class="detail-row"><strong>Book</strong><strong>Market</strong><strong>Line</strong><strong>Over</strong><strong>Under</strong><strong>Week</strong></div>
      ${props.slice(0, 18).map((row) => `
        <div class="detail-row">
          <span>${escapeHtml(row.sportsbook || row.source_name || "")}</span>
          <span>${escapeHtml(row.market || "")}</span>
          <span>${escapeHtml(formatMetric(row.line))}</span>
          <span>${escapeHtml(row.over_odds || "")}</span>
          <span>${escapeHtml(row.under_odds || "")}</span>
          <span>${escapeHtml(row.week || "")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function newsList(news) {
  if (!news.length) return emptyState("No news imported for this player.");
  return news.slice(0, 8).map((item) => `
    <div class="compact-row">
      <div>
        <strong>${escapeHtml(item.title || "News item")}</strong>
        <span>${escapeHtml(item.summary || item.published_at || "")}</span>
      </div>
      ${item.url ? `<a class="text-button" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Open</a>` : ""}
    </div>
  `).join("");
}

function renderMyTeamSelect() {
  const select = $("#my-team-select");
  if (!select) return;
  const current = state.managers.find((manager) => manager.is_me);
  select.innerHTML = `<option value="">Select my team</option>` + state.managers
    .map((manager) => `<option value="${escapeHtml(manager.roster_id)}"${current?.roster_id === manager.roster_id ? " selected" : ""}>${escapeHtml(manager.team_name || manager.display_name || `Roster ${manager.roster_id}`)}</option>`)
    .join("");
}

function renderDraftOrderMapping() {
  const container = $("#draft-order-mapping");
  if (!container) return;
  const mapping = state.draftMapping?.length
    ? state.draftMapping
    : state.draftBoard?.draft_order || [];
  if (!state.leagueId) {
    container.innerHTML = emptyState("Import your Sleeper league to review draft slots.");
    return;
  }
  if (!mapping.length) {
    container.innerHTML = emptyState("No draft-slot mapping imported yet.");
    return;
  }
  container.innerHTML = `
    <div class="draft-order-grid">
      <div class="draft-order-row header">
        <span>Draft Slot</span>
        <span>Manager</span>
        <span>Team Name</span>
        <span>Roster ID</span>
        <span>Sleeper User ID</span>
      </div>
      ${mapping.map((item) => `
        <label class="draft-order-row">
          <input
            class="draft-slot-input"
            type="number"
            min="1"
            max="32"
            value="${escapeHtml(item.draft_slot || "")}"
            data-roster-id="${escapeHtml(item.roster_id || "")}"
            data-sleeper-user-id="${escapeHtml(item.sleeper_user_id || "")}"
            data-display-name="${escapeHtml(item.display_name || "")}"
            data-team-name="${escapeHtml(item.team_name || item.manager_name || "")}"
          />
          <span>${escapeHtml(item.display_name || item.manager_name || `Roster ${item.roster_id || ""}`)}</span>
          <span>${escapeHtml(item.team_name || item.manager_name || "")}</span>
          <small>${escapeHtml(item.roster_id || "")}</small>
          <small>${escapeHtml(item.sleeper_user_id || "")}</small>
        </label>
      `).join("")}
    </div>
  `;
}

function renderImportStatus() {
  const container = $("#import-status");
  if (!container) return;
  const latest = state.setupStatus?.latest_player_import;
  const league = state.setupStatus?.league;
  const lines = [
    statusLine("Players loaded", state.setupStatus?.players_loaded ?? state.players.length),
    statusLine("Latest player import", latest ? `${latest.records_imported} records · ${latest.status}` : "Not run yet"),
    statusLine("League imported", league?.league?.name || "No league imported"),
    statusLine("Active draft ID", league?.active_draft_id || "None"),
    statusLine("Users imported", league?.users_imported ?? league?.managers_imported ?? 0),
    statusLine("Rosters imported", league?.rosters_imported ?? league?.managers_imported ?? 0),
    statusLine("Drafts imported", league?.drafts_imported ?? 0),
    statusLine("Draft picks imported", league?.draft_picks_imported ?? 0),
    statusLine("Traded picks imported", league?.traded_picks_imported ?? 0),
  ];
  container.innerHTML = lines.join("");
}

function statusLine(label, value) {
  return `<div class="compact-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderPracticeStatus() {
  const container = $("#practice-status");
  if (!container) return;
  if (!state.leagueId) {
    container.innerHTML = emptyState("Import your Sleeper league before starting a practice draft.");
    return;
  }
  if (!state.practiceStatus?.practice) {
    container.innerHTML = emptyState("No active practice draft yet. Start one to save picks through browser refresh.");
    return;
  }
  const practice = state.practiceStatus.practice;
  const picks = state.practiceStatus.picks || [];
  const lastPicks = picks.slice(-8).reverse();
  container.innerHTML = `
    <div class="compact-row">
      <span>${escapeHtml(practice.name || "Practice Draft")}</span>
      <strong>Current pick ${escapeHtml(practice.current_pick)}</strong>
    </div>
    ${lastPicks.length ? lastPicks.map((pick) => `
      <div class="compact-row">
        <span>Pick ${escapeHtml(pick.pick_no)} · ${escapeHtml(pick.manager_name || "")}</span>
        <strong>${escapeHtml(playerNameFromBoardPick(pick.pick_no) || pick.player_id || "")}</strong>
      </div>
    `).join("") : emptyState("No practice picks yet.")}
    <div class="draft-board-grid">${draftBoardHtml(state.practiceStatus.board)}</div>
  `;
}

function playerNameFromBoardPick(pickNo) {
  for (const row of state.draftBoard?.board || []) {
    const cell = (row.picks || []).find((pick) => Number(pick.pick_no) === Number(pickNo));
    if (cell?.player) return cell.player.full_name || cell.player.name;
  }
  return "";
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
  if (state.leagueId) {
    await refreshDraftState();
    return;
  }
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

async function refreshDraftState() {
  if (!state.leagueId) {
    state.draftState = null;
    state.draftBoard = null;
    state.bestAvailable = [];
    state.myPicks = [];
    state.likelyAvailable = [];
    state.rosterNeeds = [];
    state.draftMapping = [];
    state.currentPickTeam = null;
    state.isMyPick = false;
    renderDraftRoomStatus();
    renderDraftBoard();
    renderMyUpcomingPicks();
    renderRosterNeeds();
    renderDraftOrderMapping();
    return;
  }
  const query = new URLSearchParams(draftStateQueryParams());
  query.set("league_id", state.leagueId);
  const payload = await api(`/api/draft/state?${query.toString()}`);
  applyDraftState(payload);
}

function applyDraftState(payload) {
  state.draftState = payload;
  state.draftBoard = payload;
  state.draftMapping = payload.draft_mapping || payload.draft_order || state.draftMapping || [];
  state.currentPick = payload.current_pick || 1;
  state.currentPickTeam = payload.current_pick_team || null;
  state.isMyPick = Boolean(payload.is_my_pick);
  state.recommendations = payload.best_available || [];
  state.bestAvailable = payload.best_available || [];
  state.myPicks = payload.my_picks || [];
  state.likelyAvailable = payload.likely_available || [];
  state.rosterNeeds = payload.roster_needs || [];
  state.practiceStatus = {
    practice: payload.practice || null,
    picks: payload.practice_picks || [],
    board: payload,
  };
  renderStatus();
  renderDraftRoomStatus();
  renderDraftBoard();
  renderMyUpcomingPicks();
  renderRosterNeeds();
  renderRecommendations();
  renderPicks();
  renderDraftOrderMapping();
  renderPracticeStatus();
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

async function refreshPlayersSearch() {
  const query = new URLSearchParams();
  const search = $("#players-search")?.value.trim();
  const position = $("#players-position")?.value;
  const team = $("#players-team")?.value.trim();
  const ageMin = $("#players-age-min")?.value;
  const ageMax = $("#players-age-max")?.value;
  const number = $("#players-number")?.value.trim();
  const sort = $("#players-sort")?.value;
  if (search) query.set("search", search);
  if (position) query.set("position", position);
  if (team) query.set("team", team);
  if (ageMin) query.set("age_min", ageMin);
  if (ageMax) query.set("age_max", ageMax);
  if (number) query.set("number", number);
  if ($("#players-active")?.checked) query.set("active", "1");
  if (sort) query.set("sort", sort);
  query.set("limit", "75");
  state.playersSearch = await api(`/api/players/search?${query.toString()}`);
  renderPlayersTable();
}

async function refreshSetupStatus() {
  const query = new URLSearchParams();
  if (state.leagueId) query.set("league_id", state.leagueId);
  state.setupStatus = await api(`/api/setup/status?${query.toString()}`);
  state.draftMapping = state.setupStatus?.league?.draft_mapping || state.draftMapping || [];
  renderImportStatus();
  renderDraftOrderMapping();
}

async function refreshLeagueManagers() {
  if (!state.leagueId) {
    state.managers = [];
    renderMyTeamSelect();
    return;
  }
  try {
    const result = await api(`/api/league/managers?league_id=${encodeURIComponent(state.leagueId)}`);
    state.managers = result.managers || [];
    if (!state.draftMapping.length) {
      state.draftMapping = state.managers.filter((manager) => manager.draft_slot);
    }
  } catch (error) {
    state.managers = [];
  }
  renderMyTeamSelect();
  renderDraftOrderMapping();
}

async function refreshDraftBoard() {
  await refreshDraftState();
}

async function refreshPracticeStatus() {
  await refreshDraftState();
}

async function loadPlayerDetail(playerId) {
  state.selectedPlayer = await api(`/api/players/detail?player_id=${encodeURIComponent(playerId)}`);
  renderPlayerDetail();
  setActiveTab("players");
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

function draftStateQueryParams() {
  const query = new URLSearchParams();
  const position = $("#draft-position-filter")?.value;
  const search = $("#draft-search-filter")?.value.trim();
  if (position) query.set("position", position);
  if (search) query.set("search", search);
  return query;
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

function parseRows(text, label) {
  try {
    const parsed = JSON.parse(text);
    const rows = Array.isArray(parsed) ? parsed : parsed.rows;
    if (!Array.isArray(rows)) {
      toast(`${label} JSON must be an array or an object with rows.`);
      return null;
    }
    return rows;
  } catch (error) {
    toast(`${label} JSON is not valid.`);
    return null;
  }
}

function requireLeagueId() {
  if (!state.leagueId) {
    toast("Enter and import a Sleeper league ID first.");
    return null;
  }
  return state.leagueId;
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

  if (target.id === "refresh-players") {
    await refreshPlayersSearch();
    toast("Players refreshed.");
    return;
  }

  if (target.id === "refresh-waivers") {
    await refreshWaivers();
    toast("Waiver watchlist refreshed.");
    return;
  }

  if (target.id === "import-sleeper-players") {
    target.disabled = true;
    target.textContent = "Refreshing...";
    try {
      const result = await api("/api/integrations/sleeper/players/import", { method: "POST" });
      await Promise.all([refreshPlayers(), refreshPlayersSearch(), refreshDraft(), refreshSetupStatus()]);
      toast(`Refreshed ${result.imported_count} Sleeper players.`);
    } finally {
      target.disabled = false;
      target.textContent = "Refresh Sleeper Players";
    }
    return;
  }

  if (target.id === "refresh-consensus") {
    const result = await api(`/api/players/consensus?limit=25&current_pick=${encodeURIComponent(state.currentPick || 1)}`);
    await refreshDraft();
    await refreshPlayersSearch();
    toast(`Consensus refreshed for ${result.players.length} players.`);
    return;
  }

  if (target.id === "save-my-team") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const rosterId = $("#my-team-select").value;
    if (!rosterId) {
      toast("Select your team first.");
      return;
    }
    await api("/api/league/my-team", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId, roster_id: rosterId }),
    });
    await Promise.all([refreshLeagueManagers(), refreshDraftState(), refreshSetupStatus()]);
    toast("My Team saved.");
    return;
  }

  if (target.id === "save-draft-slots") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const slots = $$(".draft-slot-input").map((input) => ({
      sleeper_user_id: input.dataset.sleeperUserId || null,
      roster_id: input.dataset.rosterId ? Number(input.dataset.rosterId) : null,
      display_name: input.dataset.displayName || "",
      team_name: input.dataset.teamName || "",
      draft_slot: Number(input.value),
    }));
    const result = await api("/api/draft/slots/update", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId, slots }),
    });
    state.draftMapping = result.draft_mapping || [];
    if (result.draft_state) applyDraftState(result.draft_state);
    await Promise.all([refreshLeagueManagers(), refreshSetupStatus()]);
    toast("Draft order saved and board rebuilt.");
    return;
  }

  if (target.id === "practice-start") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api("/api/practice/start", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId }),
    });
    await refreshDraftState();
    toast("Practice draft started.");
    return;
  }

  if (target.id === "practice-sim-next") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api("/api/practice/simulate-next", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId }),
    });
    await refreshDraftState();
    toast("Simulated one pick.");
    return;
  }

  if (target.id === "practice-sim-mine") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api("/api/practice/simulate-to-my-next-pick", {
      method: "POST",
      body: JSON.stringify({ league_id: leagueId }),
    });
    await refreshDraftState();
    toast("Simulated to your next pick.");
    return;
  }

  if (target.id === "practice-reset") {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    await api(`/api/practice/reset?league_id=${encodeURIComponent(leagueId)}`, { method: "DELETE" });
    await refreshDraftState();
    toast("Practice draft reset.");
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

  const detailId = target.dataset.playerDetail;
  if (detailId) {
    await loadPlayerDetail(detailId);
    return;
  }

  if (target.dataset.removeBoardPick) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const result = await api(`/api/draft/pick?league_id=${encodeURIComponent(leagueId)}&pick_no=${encodeURIComponent(target.dataset.removeBoardPick)}`, {
      method: "DELETE",
    });
    applyDraftState(result);
    toast(`Removed pick ${target.dataset.removeBoardPick}.`);
    return;
  }

  const draftPlayer = target.dataset.draftPlayer;
  if (draftPlayer) {
    const leagueId = requireLeagueId();
    if (!leagueId) return;
    const result = await api("/api/draft/pick", {
      method: "POST",
      body: JSON.stringify({
        league_id: leagueId,
        practice_draft_id: state.practiceStatus?.practice?.id || null,
        player_id: draftPlayer,
        pick_no: null,
      }),
    });
    applyDraftState(result);
    const pick = result.last_pick;
    const playerName = pick?.player?.full_name || pick?.player?.name || "Player";
    toast(`Drafted ${playerName} at pick ${pick?.pick_no || state.currentPick}.`);
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
      player_id: player.id || player.internal_player_id,
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
  if (state.leagueId) {
    const result = await api("/api/draft/pick", {
      method: "POST",
      body: JSON.stringify({
        league_id: state.leagueId,
        practice_draft_id: state.practiceStatus?.practice?.id || null,
        player_id: player.id || player.internal_player_id,
        pick_no: $("#pick-number").value || null,
      }),
    });
    applyDraftState(result);
  } else {
    await api("/api/draft/picks", {
      method: "POST",
      body: JSON.stringify({
        player_id: player.id || player.internal_player_id,
        pick_no: $("#pick-number").value || null,
        manager: $("#pick-manager").value,
      }),
    });
    await refreshDraft();
  }
  event.target.reset();
  await refreshWaivers();
  toast("Draft pick added.");
});

if ($("#practice-pick-form")) {
  $("#practice-pick-form").addEventListener("submit", async (event) => {
    event.preventDefault();
  });
}

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
  state.leagueId = leagueId;
  window.localStorage.setItem("sleeperLeagueId", leagueId);
  state.settings = result.imported.league_settings;
  state.draftMapping = result.imported.draft_mapping || [];
  renderStatus();
  renderDraftOrderMapping();
  await Promise.all([refreshLeagueManagers(), refreshSetupStatus(), refreshDraftState()]);
  toast(`Imported ${result.imported.league?.name || "Sleeper league"}.`);
});

$("#rankings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rows = parseRows($("#rankings-json").value, "Rankings");
  if (!rows) return;
  const result = await api("/api/rankings/import/csv", {
    method: "POST",
    body: JSON.stringify({
      source_name: $("#rankings-source").value,
      rows,
    }),
  });
  await refreshPlayers();
  await refreshPlayersSearch();
  await refreshDraft();
  toast(`Imported ${result.imported_count} ${result.source_name} rankings.`);
});

$("#stats-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rows = parseRows($("#stats-json").value, "Stats");
  if (!rows) return;
  const result = await api("/api/player-stats/import/json", {
    method: "POST",
    body: JSON.stringify({
      source_name: $("#stats-source").value,
      rows,
    }),
  });
  toast(`Imported ${result.imported_count} stat rows.`);
});

$("#props-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rows = parseRows($("#props-json").value, "Props");
  if (!rows) return;
  const result = await api("/api/player-props/import/json", {
    method: "POST",
    body: JSON.stringify({
      source_name: $("#props-source").value,
      sportsbook: $("#props-book").value,
      rows,
    }),
  });
  toast(`Imported ${result.imported_count} prop rows.`);
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

["players-search", "players-team", "players-age-min", "players-age-max", "players-number"].forEach((id) => {
  $(`#${id}`).addEventListener("input", debounce(refreshPlayersSearch, 250));
});

["players-position", "players-sort", "players-active"].forEach((id) => {
  $(`#${id}`).addEventListener("change", refreshPlayersSearch);
});

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
  addMessage("assistant", "Ready. Ask me about the draft board, waiver risers, keepers, weekly matchups, or any player profile.");
}).catch((error) => {
  toast(error.message);
});
