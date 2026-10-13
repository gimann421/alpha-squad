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

---

## Results (added after all gates passed)

**Verdict: INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT.** There are 5 eligible weeks,
below the 8 the frozen rule needs to read a direction. No guardrail breach. No
material-contradiction (C) condition is met.

**Artifact:** `reports/weekly/w17_results.json`, sha256
`daf46b7631096bf645954d7d313969f0325a3dc833fd10d67f098df48f7daa5b`. It was committed (`b00e973`)
before it was read.

**Weeks 1–4 re-score identically to look 2**, to the last digit, at WR and FLEX capture@10.

**B − A, Full PPR, weeks 1–5:**

| cell | mean [95% CI] | by week | W–L–T | exact p | W10 5-week band |
|---|---:|---|---|---:|---|
| **WR capture@10** | **+0.075** [−0.008, +0.158] | −0.052 / +0.157 / +0.128 / +0.178 / **−0.035** | 3–2–0 | 0.25 | 94.6th percentile; inside [−0.039, +0.087] |
| WR capture@5 | +0.076 [+0.021, +0.130] | | 3–0–2 | 0.25 | |
| FLEX capture@10 | +0.038 [+0.006, +0.078] | +0.050 / +0.027 / +0.114 / 0 / **0** | 3–0–2 | 0.25 | 73.9th percentile |
| FLEX capture@20 | +0.044 [+0.020, +0.067] | | 4–1–0 | 0.125 | |

**How to read it:**

- **Week 5 went against B at WR capture@10** (−0.035). The 5-week mean fell from +0.103 to +0.075.
- **It is now inside W10's own predictive band.** Look 2 was above the 97.5% edge; look 3 is at
  the 94.6th percentile.
- **Still the same direction as W10** (2021–2025: +0.022 [+0.007, +0.038]). That is consistent
  with W10, not a replication.
- **At FLEX, B and A had identical top 10s in weeks 4 and 5** (overlap 1.0).
- **Half-PPR agrees:** WR capture@10 +0.077 (95.1st percentile); FLEX +0.040.
- **Shuffled-feature null:** WR capture@10 +0.016. B − N is about +0.059.

## Gates

**All 12 W14 gates pass,** in the same two-pass split as look 2:

- pass 1: G1, G2, G4–G11;
- final pass: G1–G5, G7–G10, G12, on the same artifact.

| gate | look 3 |
|---|---|
| G1 parity | production's 2026 predictions **1,596 / 1,596** exact; 2021–2025 **26,097 / 26,097** exact |
| G2 W10 frozen | no file on W10's path changed since `5de17c1`; one `w10.trainings` call; no own fit |
| G3 history | training frames and durable table identical. W10's 2021–2025 re-run differs only in the 2025 weeks already explained by the 13 revised crosswalk mappings (A4), the same as look 2 |
| G4 anti-peek | base database unmodified (`fa8e32db…`); no 2026 outcome rows in it; no NGS reader |
| G5 walk-forward | no 2026 row in any training frame |
| G6 later weeks | with every later week deleted, features and A/B predictions are bit-identical for weeks 1–5 (320 / 320 / 326 / 324 / 306 player-weeks) |
| G7 inputs | only W10's 7 frozen columns added |
| G8 eligibility | evaluated = eligible = weeks 1–5; schedule sha matches |
| G9 identity | 0 / 1,629 evaluated players without a canonical record |
| G10 W10's own numbers | 6,150 values equal to the verbatim W10 2026 run, 0 mismatches |
| G11 determinism | two runs byte-identical (`daf46b76…`) |
| G12 upstream | W5–W13 (14 artifacts) byte-identical |

**About G12's evidence.** G12 uses W15's W5–W13 byte-identical record, with no rerun:

- the base database is the same file (`fa8e32db…`);
- since that record, the only code changes under `src/` or `scripts/research/` are the new
  `alpha_squad/beta` files, which no research module imports (`tests/beta/test_isolation.py`);
- W16 re-confirmed W10, W14 and W15 byte-identical on this base.

## Scope

Research only. **Production diff EMPTY**; no model, feature or protocol change. No PR, no merge.

## Next

- Continue the unchanged protocol as weeks complete.
- **The first look that can read a direction needs ≥ 8 weeks**, which is week 8 at the earliest.
- The final look after week 17 applies W10 §9 once.
- **Separately:** fix the `build_rookie_features` NOT NULL defect in production. It is not on the
  holdout path.
