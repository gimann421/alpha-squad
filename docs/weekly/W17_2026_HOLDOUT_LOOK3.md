# W17 — 2026 holdout, look 3 (W14 protocol, unchanged)

**Status: FROZEN BEFORE SCORING.** This section was committed before any look-3 comparison was
computed. The results sections are added after every gate passes.

## Freeze record (2026-10-13)

**Protocol:** `docs/weekly/W14_PREREGISTRATION.md` §2–§7 and §10, with amendments A1–A5. No new
amendment.

**Base database:** the verified original `data/alpha_squad.duckdb`, sha256
`fa8e32dbbb8942d890d38f0fad5c88981dc7f171238826abf13eb09ddd2a73c7` (D125). D124's option (a)
therefore holds: no rebuilt base is used.

**Fresh isolated copy:** `data/w16/alpha_squad_2026.duckdb`. Its sha256 at the copy was
`fa8e32db…2a73c7`, the same as the base. The base was not written.

**Data path:** §3 steps 1–5, with A1 and A2, in that copy, with `ALPHA_SQUAD_DATA_DIR=data/w16`.

- **Schedule snapshot:** captured 2026-10-13T13:01:46Z, sha256
  `b58b25eda550a21d297d3d731a27c461fb07894b555500e0bc8e02d3aee9cc37`.
- **2026 outcome snapshots:** captured 2026-10-13T13:02:47Z.
- **A2's row-order restore:** production's loader returns the canonical 2015–2025 sequence for
  QB, RB, WR and TE.

**Data-path deviation, recorded before scoring.** `features build` exited 1 in its **last**
sub-step, `build_rookie_features`, with
`NOT NULL constraint failed: rookie_features.breakout_top24`. Look 2 ran the same step without
error (1,133 rows), so newly ingested 2026 data triggered it.

- **What did not change:** production code is unchanged and nothing was re-run.
- **What had already been built:** every earlier sub-step completed and committed before the
  failing statement, through week 5. That covers `games`, `player_week_stats`, K/DST scoring,
  `player_week_features`, `team_week_stats`, `team_week_points` and `team_week_features`.
- **Why it doesn't affect this look:** no module on the holdout path reads `rookie_features`.
  `grep` over `scripts/research/`, `src/alpha_squad/evaluation/`,
  `src/alpha_squad/models/established/` and `src/alpha_squad/models/baselines/` finds no reference.
- **Status:** a production defect to fix separately; it is not part of this look.

**Eligible weeks, from the committed §4 rule only** (schedule, games present, teams with stats,
board; no outcome values):

| week | Friday board | games in data | last kickoff (UTC) | status |
|---:|---|---:|---|---|
| 1–4 | 09-11, 09-18, 09-25, 10-02 | 16 / 16 each | ≤ 10-06 00:15 | already in looks 1–2 |
| **5** | **10-09** | **15 / 15** | 10-13 00:15 (+6 h ≤ capture 13:02) | **newly eligible** |
| 6–17 | — | 0 | — | not yet played |

**n = 5 < 8.** By §7, this look can only return INCONCLUSIVE — CONTINUE, unless a
material-contradiction condition (C) is met.
