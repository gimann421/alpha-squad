# W12 — Data availability and leakage audit

**Status: AUDIT, written before any W12 outcome was computed.** It records sources, timing and
coverage facts only. No breakout, board or model comparison was computed to write it.

**The question it answers:** what information could a researcher *verifiably* have had by the
Friday cutoff, 2021–2025, about why a running back's role is changing?

**Source classes:**

- **CLASS A:** a verified timestamp at or before the cutoff. Only Class A may enter the primary
  test.
- **CLASS B:** historical data exists, but its timing relative to the cutoff cannot be
  established.
- **CLASS C:** only final or post-week information, or no reconstructable history at all. Never a
  feature.

---

## 1. The cutoff, made exact

**The program's cutoff (W2 §4):** "information whose timestamp is at or before the snapshot date".
The snapshot is the canonical weekly board: 78 of the 79 evaluated weeks are Fridays, and one is a
Saturday.

**W12 makes this an instant:**

> **cutoff(week) = 23:59:59 America/New_York on the Friday before the week's first Sunday game.**

- That Friday equals the canonical snapshot date in 78 of 79 weeks.
- In the one week whose board is a Saturday, the Friday is used, which is stricter.
- The benchmark ECR board's own intraday scrape time is unknown. That does not matter here,
  because ECR is not an input.

**Pre-registered strict sensitivity:** 00:00:00 ET on that Friday, which excludes the Friday
final injury report. This is W9's "strictly before the cutoff date" rule.

---

## 2. Sources investigated

| # | source | dates | timestamp | publication or update? | history reconstructable? | class |
|---|---|---|---|---|---|---|
| 1 | **NFL official injury report via nflverse `injuries`** | 2015–2024 | `date_modified`, UTC, to the second, **on 100% of rows** | the row's **last modification** | yes: one final row per player-week, with its last-edit time | **A** for rows last modified ≤ cutoff |
| 2 | nflverse `injuries` 2025 | 2025 | **no timestamp column** | — | no | **B** |
| 3 | **ESPN depth charts via nflverse `depth_charts` 2025** | Aug 2025 – Mar 2026 | `dt`, a **daily capture** at about 07:00 UTC, 221 captures | capture time | yes: dated daily snapshots | **A** for captures ≤ cutoff |
| 4 | nflverse `depth_charts` 2015–2024 | weekly | **none**: keyed by week only | unknown | the week-*w* chart's timing is unknown | **B**. The *previous* week's chart is A by construction but stale; it is already W7's `depth_team_prior` |
| 5 | nflverse `weekly_rosters` (`status`: ACT, RES = reserve/IR, INA, …) | 2015–2025 | none | unknown | no | **B** |
| 6 | FantasyPros news API v2 (project key, D37) | live | `created`, UTC | publication | **no**: returns only the latest ~10 items, ignoring offset, page, date and player filters | **C** for 2021–2025 (forward-only) |
| 7 | Sleeper API | live | — | — | current state and trending only | **C** |
| 8 | ESPN public API | — | — | — | HTTP 403 (known, D31) | unavailable |
| 9 | Internet Archive Wayback Machine (NFL injury pages, Ourlads/team depth charts, news pages) | sporadic | capture time | capture | in principle, yet **`web.archive.org` is blocked by this environment's egress policy** (only the `archive.org` availability lookup answers). Captures are also sporadic: `nfl.com/injuries/league/2023/REG5`'s nearest capture is 2023-10-08, *after* that Friday | not reproducible here: **C** |
| 10 | Ourlads depth charts | live | — | — | only via Wayback (blocked) | **C** |
| 11 | coach statements, team announcements, beat reporters (X/Twitter, team sites) | — | — | — | **no accessible historical, timestamped archive** | **untestable** |
| 12 | nflverse `trades` | day-level dates | trade date | publication | yes | A at day level. **Not used:** mid-season RB trades are too rare to matter |
| 13 | Pro Football Reference transactions (IR placements) | dated | — | — | the site's terms forbid automated scraping | **excluded** (never bypass access controls) |
| 14 | nflverse `pbp`, `snap_counts`, `participation`, `ftn_charting` | post-game | game time | — | — | **C** for week *w* (history only) |

**Categories the brief asks about:**

| category | status |
|---|---|
| **A. injury / practice** | **Class A for 2021–2024** (source 1). This includes teammate availability. Only the final version of each report row exists: **no day-by-day history**, so "status changed during the week" cannot be reconstructed |
| **B. depth charts** | **Class A only for 2025** (source 3, 16 evaluated weeks). 2021–2024 is Class B |
| **C. news, coach and beat-reporter role information** | **no reconstructable Class A source**, so this category cannot be tested (sources 6, 9–11) |
| **D. other** | nothing relevant, reproducible and Class A |

---

## 3. The injury report: timing and leakage audit

**Timezone.** `date_modified` is `TIMESTAMP WITH TIME ZONE` in UTC and is converted to
America/New_York for every comparison. Most values cluster at Friday about 19:50 UTC (15:50 ET),
the league's Friday final-report release.

**Publication vs update.** It is a **last-modified** time. So:

- **a row last modified ≤ cutoff** holds content that existed by the cutoff and was never changed
  afterwards;
- **a row modified after the cutoff** has lost its pre-cutoff state. It is treated as **unknown**,
  never as healthy.

**Retrospective edits.**

- Of 51,548 matched 2015–2024 rows, 51,500 were last modified before their team's game day, 25
  on game day and **23 after the game (0.04%)**.
- No row in any season was modified after that season's final regular-season week.
- The source is not retro-edited.

**Timing vs the cutoff, RB/WR/TE rows** (dates in ET):

| season | before the snapshot day | on it (Friday report) | after |
|---|---:|---:|---:|
| 2021 | 268 | 1,033 | 95 |
| 2022 | 237 | 978 | 96 |
| 2023 | 244 | 984 | 108 |
| 2024 | 161 | 940 | 123 |

**About 92% of rows are Class A under the primary cutoff; 17% under the strict one.**

**Structural limits.**

- **Players on injured reserve are not on the weekly report.** A long-term vacancy (starter on IR)
  is invisible in Class A; it appears only in Class B `weekly_rosters`.
- **Team codes:** 2015–2019 rows use OAK, SD and STL, while stats and games use LV, LAC and LA. A
  fixed alias map is applied and asserted.
- 2025 has no timestamps, so no injury feature exists for 2025 (missing, never filled).

**Reproducibility.**

- nflverse release assets `injuries_<season>.parquet` are recorded in `snapshot_registry` with
  sha256 and capture time.
- Raw files stay under `data/` (gitignored) and are re-fetched with `alpha-squad ingest`.
- No manual spreadsheets.

---

## 4. Coverage of the W12 question (2021–2024, RB, evaluated universe, primary cutoff)

| | player-weeks |
|---|---:|
| RB universe | 4,717 |
| … whose team's week-*w* report is observable by the cutoff | 4,442 (94%) |
| **sustained RB risers (W11 PRIMARY `ROLE_UP`)** | **710** (2021: 183, 2022: 139, 2023: 222, 2024: 166) |
| … with an observable team report | 666 (94%) |
| … with any same-team RB listed Out/Doubtful by the cutoff | 74 (10%) |
| … with a same-team RB listed Out/Doubtful who averaged **≥ 8 touches/game** this season | **39** (2021: 8, 2022: 4, 2023: 14, 2024: 13) |

**The information that would most plausibly separate a real breakout from a blip is a vacancy
created by a teammate's absence this week. It is present, verifiably before Friday, for about 5%
of risers.** The rest of the relevant variation is either already in the box score (a starter out
for weeks has already ceded the touches that made the player a riser) or in Class B (IR status,
current-week depth charts).

**2025 depth charts** (source 3; 16 evaluated weeks, RB risers only):

- every week has a capture before its cutoff, at most 21 hours before it;
- 120 risers, all listed;
- 71 are listed RB1;
- **only 5 were promoted and 2 demoted** in the week before the cutoff.

**A depth-chart *change* signal is too sparse to test.**

**Breakout counts are outcomes and were not computed for this audit.** The pre-registration fixes
a minimum-events gate that the runner checks before anything is interpreted.

---

## 5. Consequences for W12's design

1. The primary Class A features come from **source 1 alone**:
   - teammate availability (Out/Doubtful, Questionable, returning);
   - the player's own designation and practice participation.
2. **The primary window is 2021–2024 (63 evaluated weeks)**, where that source exists. The 79-week
   window is secondary: 2025 has no Class A injury data.
3. **Depth charts:**
   - Class A exists only in 2025. A walk-forward model trained through 2024 cannot learn from it,
     so it is tested only as information (Question A), on 16 weeks.
   - **2021–2024 current-week depth charts and weekly-roster reserve status are Class B.** They may
     enter only one labelled exploratory arm, never the verdict.
4. **News, coach and beat-reporter information is untestable** with any source reachable here. W12
   will say so rather than infer it.
