# W15 — 2026 holdout, look 2 (W14 protocol, unchanged)

**Status: FROZEN BEFORE SCORING.** This section was committed before any look-2 comparison was
computed. The results sections are added after every gate passes.

## Freeze record (2026-10-10)

**Protocol:** `docs/weekly/W14_PREREGISTRATION.md` §2–§7 and §10, with amendments A1–A5. A5 is
tooling only.

**Data path:** §3 steps 1–5 in a fresh isolated database, `data/w15/alpha_squad_2026.duckdb`. The
data was captured 2026-10-10 at 23:00 UTC; the schedule snapshot's sha256 is `ea76320b…`. The
canonical database is untouched (sha256 `fa8e32db…`).

**A2's row-order restore:** production's loader returns the canonical 2015–2025 sequence for QB,
RB, WR and TE.

**Eligible weeks, from the committed §4 rule only** (schedule, games present, teams with stats;
no outcome values):

| week | Friday board | games in data | status |
|---:|---|---:|---|
| 1–3 | 09-11, 09-18, 09-25 | 16 / 16 each | already in look 1 |
| **4** | 10-02 | **16 / 16** | **newly eligible** |
| 5 | none yet | 1 / 15 | pending (games unplayed; no canonical board in the ECR history yet) |
| 6–17 | — | 0 | not yet played |

**n = 4 < 8.** By §7, this look can only return INCONCLUSIVE — CONTINUE, unless a
material-contradiction condition (C) is met.
