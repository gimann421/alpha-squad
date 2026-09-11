# D88 — O1-FULL at 10 slots: a power / replication experiment

*Not a new objective. The only change from D86/D87 is the number of draft slots.
`models/` and `league/` are **byte-identical to Y1** throughout.*

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| working tree | clean |
| HEAD | `cacd857` (D87 results) |
| `league/` + `models/` vs `origin/main` | **byte-identical to Y1** |
| D86/D87 artifacts | present (`otiers2.json`, `d87arms.json`, `equiv.json`) |
| database | intact (231 MB) |
| `shortlist_k` default | `None` in both `_pick_by_tier` and `simulate_forensic_draft` |
| shortlist engagement | only when explicitly set **and** the tier is the expensive one |

No production behaviour was modified. No production change was prepared.

---

## 2. D86/D87 reproduction (Phase 1)

Before committing to a multi-hour run, O1-FULL was re-run on three (format, season, slot) cells
and compared against the D87 artifact. `shortlist_k` was omitted entirely, so the whole board is
scored.

| case | arm | metric | D87 | D88 | Δ | roster |
|---|---|---|---|---|---|---|
| target 2024 s1 | O0 | weekly (no foresight) | 1892.5 | 1892.5 | +0.0000 | SAME |
| target 2024 s1 | O0 | season-long | 1954.9 | 1954.9 | +0.0000 | SAME |
| target 2024 s1 | **O1-FULL** | weekly (no foresight) | 2181.6 | 2181.6 | +0.0000 | SAME |
| target 2024 s1 | **O1-FULL** | season-long | 2203.5 | 2203.5 | +0.0000 | SAME |
| target 2022 s7 | O0 | weekly (no foresight) | 2278.6 | 2278.6 | +0.0000 | SAME |
| target 2022 s7 | O1-FULL | weekly (no foresight) | 2212.8 | 2212.8 | +0.0000 | SAME |
| legacy 2023 s4 | O0 | weekly (no foresight) | 2184.8 | 2184.8 | +0.0000 | SAME |
| legacy 2023 s4 | O1-FULL | weekly (no foresight) | 2194.3 | 2194.3 | +0.0000 | SAME |

**PASS — identical drafted rosters and identical metrics to the decimal.** The harness is
deterministic and carries no accidental shortlist.

---

## 3. Experiment design (Phase 2)

| | D86 / D87 | **D88** |
|---|---|---|
| draft slots | 4 (1, 4, 7, 10) | **10 (1–10)** |
| seasons | 2021–2025 | 2021–2025 (unchanged) |
| formats | target 1QB, legacy 2QB | unchanged |
| candidate set | full board | **full board (no shortlist)** |
| objective | `E[weekly MSV] + 1.0·daVORP` | unchanged |
| opponent, scoring, gates, metrics | — | unchanged |

Slots 1–10 **superset** D86/D87's four, so that subset is a built-in reproduction check inside
the same run.

*Results, power analysis and gates follow below once the run completes.*
