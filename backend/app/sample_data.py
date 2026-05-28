"""Seed data used until live feeds are configured.

These are intentionally lightweight sample projections. Real deployments should
replace or blend them with fresh projections, injury feeds, depth charts, odds,
and league import data.
"""

from __future__ import annotations

from .models import Player


SAMPLE_PLAYERS: list[Player] = [
    Player("p_qb_allen", "Josh Allen", "QB", "BUF", 374.6, 23.8, 31, 7, snap_share=0.98, trend_score=7.1, rostered_pct=99, odds_signal="High implied team total", notes="Elite rushing baseline keeps weekly ceiling high."),
    Player("p_qb_lamar", "Lamar Jackson", "QB", "BAL", 368.2, 27.4, 36, 7, snap_share=0.98, trend_score=7.0, rostered_pct=99, odds_signal="Favorable rushing script", notes="Dual-threat profile creates weekly edge in 4-point pass TD formats."),
    Player("p_qb_hurts", "Jalen Hurts", "QB", "PHI", 358.9, 32.1, 43, 9, snap_share=0.98, trend_score=6.7, rostered_pct=99, odds_signal="Strong red-zone offense", notes="Goal-line rushing makes him a premium fantasy QB."),
    Player("p_qb_burrow", "Joe Burrow", "QB", "CIN", 331.5, 58.0, 71, 10, snap_share=0.99, trend_score=5.5, rostered_pct=96, odds_signal="Pass-heavy environment", notes="Stackable with elite receivers in shootout games."),
    Player("p_qb_mahomes", "Patrick Mahomes", "QB", "KC", 327.2, 60.6, 74, 10, snap_share=0.99, trend_score=5.3, rostered_pct=97, odds_signal="Stable favorite", notes="Floor remains strong even when rushing volume is modest."),
    Player("p_qb_stroud", "C.J. Stroud", "QB", "HOU", 314.8, 86.4, 95, 6, snap_share=0.99, trend_score=6.0, rostered_pct=91, odds_signal="Positive passing volume", notes="Young offense with room for efficiency growth."),
    Player("p_rb_bijan", "Bijan Robinson", "RB", "ATL", 288.3, 5.0, 5, 5, snap_share=0.78, target_share=0.15, carry_share=0.64, trend_score=8.6, rostered_pct=100, odds_signal="Positive game script", notes="Three-down role and receiving profile create RB1 overall upside."),
    Player("p_rb_barkley", "Saquon Barkley", "RB", "PHI", 281.1, 6.8, 7, 9, snap_share=0.73, target_share=0.11, carry_share=0.61, trend_score=8.3, rostered_pct=100, odds_signal="High red-zone equity", notes="Premium offense plus explosive workload."),
    Player("p_rb_gibbs", "Jahmyr Gibbs", "RB", "DET", 276.4, 8.7, 9, 8, snap_share=0.68, target_share=0.17, carry_share=0.48, trend_score=8.4, rostered_pct=100, odds_signal="High implied team total", notes="Receiving usage lifts PPR floor."),
    Player("p_rb_mccaffrey", "Christian McCaffrey", "RB", "SF", 268.0, 13.0, 14, 14, injury_status="Monitor", snap_share=0.70, target_share=0.16, carry_share=0.54, trend_score=6.9, rostered_pct=100, odds_signal="Efficient offense", notes="Still an elite role when healthy; injury risk should be priced in."),
    Player("p_rb_hall", "Breece Hall", "RB", "NYJ", 253.2, 17.5, 20, 9, snap_share=0.71, target_share=0.14, carry_share=0.58, trend_score=7.4, rostered_pct=100, odds_signal="Neutral", notes="Workhorse path with explosive receiving upside."),
    Player("p_rb_achane", "De'Von Achane", "RB", "MIA", 238.9, 23.0, 28, 12, snap_share=0.56, target_share=0.13, carry_share=0.39, trend_score=7.8, rostered_pct=99, odds_signal="Explosive offense", notes="Volatility is real, but efficiency can win weeks."),
    Player("p_rb_taylor", "Jonathan Taylor", "RB", "IND", 232.0, 25.4, 32, 11, snap_share=0.69, target_share=0.08, carry_share=0.61, trend_score=6.2, rostered_pct=99, odds_signal="Run-leaning script", notes="Carries and goal-line work drive value."),
    Player("p_rb_williams", "Kyren Williams", "RB", "LAR", 226.5, 33.0, 45, 8, snap_share=0.72, target_share=0.10, carry_share=0.58, trend_score=6.8, rostered_pct=98, odds_signal="Positive home split", notes="Volume profile beats raw athleticism concerns."),
    Player("p_rb_brown", "Chase Brown", "RB", "CIN", 184.4, 73.0, 82, 10, snap_share=0.59, target_share=0.11, carry_share=0.43, trend_score=8.1, rostered_pct=74, odds_signal="Pass-game spike", notes="Usage trend points toward more high-value touches."),
    Player("p_rb_wright", "Jaylen Wright", "RB", "MIA", 128.8, 145.0, 156, 12, snap_share=0.23, target_share=0.04, carry_share=0.15, trend_score=7.6, rostered_pct=31, odds_signal="Contingent upside", notes="Explosive backup with rising depth-chart leverage."),
    Player("p_wr_chase", "Ja'Marr Chase", "WR", "CIN", 304.8, 2.6, 2, 10, snap_share=0.93, target_share=0.29, trend_score=8.8, rostered_pct=100, odds_signal="Shootout potential", notes="Alpha target share with elite touchdown ceiling."),
    Player("p_wr_jefferson", "Justin Jefferson", "WR", "MIN", 295.4, 4.0, 4, 6, snap_share=0.94, target_share=0.30, trend_score=8.4, rostered_pct=100, odds_signal="Volume-proof", notes="Target dominance keeps him matchup resistant."),
    Player("p_wr_lamb", "CeeDee Lamb", "WR", "DAL", 291.1, 6.2, 6, 10, snap_share=0.93, target_share=0.28, trend_score=8.1, rostered_pct=100, odds_signal="High passing share", notes="Slot and perimeter usage creates stable reception floor."),
    Player("p_wr_stbrown", "Amon-Ra St. Brown", "WR", "DET", 283.7, 9.5, 10, 8, snap_share=0.91, target_share=0.27, trend_score=8.0, rostered_pct=100, odds_signal="High implied team total", notes="PPR machine in one of the league's most stable offenses."),
    Player("p_wr_nacua", "Puka Nacua", "WR", "LAR", 273.6, 12.0, 13, 8, snap_share=0.92, target_share=0.27, trend_score=7.6, rostered_pct=100, odds_signal="Target funnel", notes="Volume and yards-after-catch role remain premium."),
    Player("p_wr_collins", "Nico Collins", "WR", "HOU", 246.2, 24.2, 30, 6, snap_share=0.88, target_share=0.23, trend_score=7.2, rostered_pct=99, odds_signal="Rising pass offense", notes="Explosive efficiency with touchdown upside."),
    Player("p_wr_nabers", "Malik Nabers", "WR", "NYG", 241.0, 26.8, 34, 14, snap_share=0.91, target_share=0.28, trend_score=7.9, rostered_pct=99, odds_signal="Negative script volume", notes="Commanding target share can offset team efficiency concerns."),
    Player("p_wr_thomas", "Brian Thomas Jr.", "WR", "JAX", 232.9, 37.5, 48, 8, snap_share=0.88, target_share=0.23, trend_score=8.2, rostered_pct=96, odds_signal="Big-play market support", notes="Downfield role is turning into bankable weekly volume."),
    Player("p_wr_london", "Drake London", "WR", "ATL", 228.0, 39.0, 50, 5, snap_share=0.90, target_share=0.25, trend_score=7.0, rostered_pct=97, odds_signal="Red-zone usage rising", notes="Alpha profile benefits if passing efficiency climbs."),
    Player("p_wr_brown", "A.J. Brown", "WR", "PHI", 224.3, 41.0, 53, 9, snap_share=0.89, target_share=0.24, trend_score=6.4, rostered_pct=98, odds_signal="Strong favorite", notes="Touchdown equity and explosive plays keep ceiling intact."),
    Player("p_wr_shakir", "Khalil Shakir", "WR", "BUF", 159.7, 121.0, 132, 7, snap_share=0.75, target_share=0.17, trend_score=8.0, rostered_pct=57, odds_signal="Role consolidation", notes="Routes and efficiency are moving in the right direction."),
    Player("p_wr_wicks", "Dontayvion Wicks", "WR", "GB", 136.5, 160.0, 178, 5, snap_share=0.52, target_share=0.14, trend_score=7.3, rostered_pct=28, odds_signal="Depth-chart volatility", notes="Worth monitoring if route share rises."),
    Player("p_te_bowers", "Brock Bowers", "TE", "LV", 232.6, 22.1, 27, 8, snap_share=0.88, target_share=0.25, trend_score=8.7, rostered_pct=100, odds_signal="Target funnel", notes="Rare tight end target share makes him a positional edge."),
    Player("p_te_mcbride", "Trey McBride", "TE", "ARI", 214.4, 31.5, 41, 8, snap_share=0.86, target_share=0.24, trend_score=8.0, rostered_pct=99, odds_signal="Middle-field mismatch", notes="Reception floor is elite for the position."),
    Player("p_te_kittle", "George Kittle", "TE", "SF", 184.0, 56.0, 68, 14, snap_share=0.84, target_share=0.18, trend_score=5.9, rostered_pct=98, odds_signal="Efficient touchdown profile", notes="Weekly volatility but big ceiling."),
    Player("p_te_laporta", "Sam LaPorta", "TE", "DET", 181.7, 62.0, 77, 8, snap_share=0.82, target_share=0.18, trend_score=6.3, rostered_pct=98, odds_signal="High implied team total", notes="Touchdown environment supports bounce-back weeks."),
    Player("p_te_kelce", "Travis Kelce", "TE", "KC", 176.3, 72.0, 86, 10, snap_share=0.78, target_share=0.19, trend_score=5.1, rostered_pct=97, odds_signal="Playoff role preservation", notes="Still useful if price accounts for age curve."),
    Player("p_te_andrews", "Mark Andrews", "TE", "BAL", 170.6, 83.0, 97, 7, snap_share=0.76, target_share=0.18, trend_score=5.4, rostered_pct=96, odds_signal="Red-zone role", notes="Touchdown access remains his main value driver."),
    Player("p_te_likely", "Isaiah Likely", "TE", "BAL", 111.4, 172.0, 188, 7, snap_share=0.48, target_share=0.11, trend_score=7.4, rostered_pct=35, odds_signal="Two-TE package growth", notes="Cheap upside if role expands or Andrews misses time."),
    Player("p_def_pit", "Pittsburgh Steelers", "DEF", "PIT", 142.0, 143.0, 160, 5, snap_share=1.0, trend_score=6.8, rostered_pct=82, odds_signal="Pressure advantage", notes="Sack profile creates weekly splash-play chances."),
    Player("p_def_phi", "Philadelphia Eagles", "DEF", "PHI", 139.5, 148.0, 165, 9, snap_share=1.0, trend_score=6.2, rostered_pct=78, odds_signal="Favorite with pass rush", notes="Best when opponent is forced into catch-up mode."),
    Player("p_def_bal", "Baltimore Ravens", "DEF", "BAL", 137.2, 151.0, 169, 7, snap_share=1.0, trend_score=6.0, rostered_pct=76, odds_signal="Low opponent total", notes="Strong weekly floor against mistake-prone passers."),
    Player("p_def_nyj", "New York Jets", "DEF", "NYJ", 135.0, 154.0, 172, 9, snap_share=1.0, trend_score=5.9, rostered_pct=74, odds_signal="Low total", notes="Coverage strength supports turnover upside."),
    Player("p_def_sf", "San Francisco 49ers", "DEF", "SF", 133.8, 158.0, 177, 14, snap_share=1.0, trend_score=5.6, rostered_pct=70, odds_signal="Positive home split", notes="Still streamable when favored."),
    Player("p_k_aubrey", "Brandon Aubrey", "K", "DAL", 154.0, 149.0, 166, 10, snap_share=1.0, trend_score=6.6, rostered_pct=88, odds_signal="Dome games and drive volume", notes="Premium range and offense volume."),
    Player("p_k_butker", "Harrison Butker", "K", "KC", 146.5, 162.0, 180, 10, snap_share=1.0, trend_score=5.6, rostered_pct=74, odds_signal="Favorite with red-zone trips", notes="Stable offense keeps attempts alive."),
    Player("p_k_elliott", "Jake Elliott", "K", "PHI", 145.0, 164.0, 183, 9, snap_share=1.0, trend_score=5.5, rostered_pct=72, odds_signal="High implied team total", notes="Useful when Philadelphia projects for scoring volume."),
    Player("p_k_dicker", "Cameron Dicker", "K", "LAC", 143.6, 168.0, 189, 12, snap_share=1.0, trend_score=6.2, rostered_pct=58, odds_signal="Attempt volume", notes="Quietly strong if offense stalls near field-goal range."),
    Player("p_k_fairbairn", "Ka'imi Fairbairn", "K", "HOU", 142.8, 171.0, 192, 6, snap_share=1.0, trend_score=6.0, rostered_pct=55, odds_signal="Rising offense", notes="Beneficiary of improving drive quality."),
]


def players_by_id() -> dict[str, Player]:
    return {player.id: player for player in SAMPLE_PLAYERS}
