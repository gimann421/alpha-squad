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

---

## 4. Sample size (Phase 3)

| | target 1QB | legacy 2QB |
|---|---|---|
| paired draft observations | **50** | **50** |
| season clusters | **5** | **5** |
| slots per season | 10 | 10 |
| drafts run (both arms) | 100 | 100 |

200 drafts total. D86/D87 ran 40 per format; D88 runs 100.

---

## 5. Historical results (Phase 4/5)

### Target format (10-team 1-QB PPR)

| arm | weekly (no foresight) — primary | weekly (hindsight) | season-long | total roster | bench | unfilled |
|---|---|---|---|---|---|---|
| O0 (Y1) | 1923.0 | 2093.3 | 1963.6 | 2692.1 | 392.2 | 0 |
| **O1-FULL** | **1973.6** | **2169.0** | **2003.5** | 2672.4 | 414.8 | 0 |
| **Δ** | **+50.5** | **+75.7** | **+39.9** | **−19.8** | **+22.6** | — |

Per season: 2021 **+57.3**, 2022 −10.4, 2023 +21.0, 2024 **+90.8**, 2025 **+94.0** — **4 of 5
seasons improved**. Clustered 95% CI **[−5.5, +106.6]**. Leave-one-season-out all positive
(+39.7 … +65.8).

### Legacy 2QB dynasty

| arm | weekly (no foresight) | weekly (hindsight) | season-long | total roster |
|---|---|---|---|---|
| O0 (Y1) | 2213.5 | 2477.3 | 2151.2 | 3050.6 |
| **O1-FULL** | **2211.2** | **2502.4** | **2167.5** | 3101.8 |
| **Δ** | **−2.3** | **+25.1** | **+16.2** | **+51.1** |

Per season: −87.5, +44.3, +40.2, +53.6, −62.2 — 3 of 5 improved. CI **[−85.5, +80.8]**.

---

## 6. Replication: D86/D87 vs D88 (Phase 4)

Slots 1–10 superset D86/D87's (1, 4, 7, 10), so the subset is a built-in control:

| | target 1QB | legacy 2QB |
|---|---|---|
| D87 4-slot (artifact) | +52.9, CI [−8.3, +114.0] | +1.6, CI [−56.9, +60.1] |
| **D88 4-slot subset (re-run)** | **+52.9, CI [−8.3, +114.0] — IDENTICAL** | **+1.6, CI [−56.9, +60.1] — IDENTICAL** |
| D88 all 10 slots | **+50.5**, CI [−5.5, +106.6] | **−2.3**, CI [−85.5, +80.8] |

**The effect replicates.** Target moved +52.9 → +50.5 (−2.4) on 2.5× the data; the sign, the
magnitude, the positional behaviour and the 2026 implications are all preserved. Legacy remains an
effective null (+1.6 → −2.3). Nothing shrank toward zero in the target format, and nothing grew.

---

## 7. Power — the decisive finding (Phase 3)

Decomposing the paired difference's variance (target format):

| source | SD |
|---|---|
| **between-season** (5 clusters) | **45.1** |
| within-season (across 10 slots) | 55.7 |

The clustered SE is `sqrt(between² + within²/n) / sqrt(5)`. Adding slots shrinks only the second
term, so:

| slots per season | SE | **MDE** |
|---|---|---|
| 4 (D86/D87) | 23.7 | **65.8** |
| **10 (D88)** | **21.7** | **60.1** |
| 20 | 20.9 | 58.1 |
| 100 | 20.3 | 56.4 |
| **∞** | **20.2** | **56.0** |

**The MDE converges to ≈ 56 points no matter how many draft slots are added**, because the
between-season variance is irreducible at 5 seasons. The observed effect is **+50.5**, which sits
**below that asymptote**.

> **Adding draft slots cannot resolve O1. It was never going to.** Going 4 → 10 slots bought a 9%
> reduction in MDE (65.8 → 60.1); going to 100 slots would buy 5% more. The binding constraint is
> the number of **seasons**, not slots.

### What would resolve it

With between-season SD 45.1 held fixed, `MDE = t(df=n−1) × 45.1 / √n`:

| seasons | MDE |
|---|---|
| 5 (now) | 56.0 |
| **6** | **47.3** |
| 7 | 41.7 |
| 8 | 37.7 |

**Exactly one additional season is available.** The benchmark's usable universe is **2020–2025**:
2020 carries 612 board players, while 2019 has only 174 (no established-player projections at all).
So the reachable configuration is **6 seasons**, giving MDE ≈ 47.3 against an effect of ≈ 50.5 — a
margin of about **3 points**. That is the only remaining experiment that could resolve O1 on this
benchmark, and it would resolve it by a hair, contingent on 2020 not raising the between-season SD.

---

## 8. Gate results (Phase 4) — D86's gates, unchanged

| gate | target 1QB | legacy 2QB |
|---|---|---|
| G2 infeasibility ≤ control | **ok** (0 vs 0) | **ok** (0 vs 0) |
| G3 ≤ 1 season worse | **ok** (1/5) | **FAIL** (2/5) |
| G6 leave-one-season-out | **ok** (all +) | **FAIL** |
| G7 cross-format sign | — | **FAIL** (+50.5 → −2.3) |
| G8 clustered CI excludes 0 | **FAIL** [−5.5, +106.6] | **FAIL** |
| G9 margin ≥ 25 | **ok** (+50.5) | **FAIL** (−2.3) |
| G10 season-long ≥ −25 | **ok** (+39.9) | **ok** (+16.2) |

**In the target format only G8 fails, and it fails by 5.5 points.** In legacy the arm is a null.

---

## 9. Positional behaviour (Phase 5) and K/DST (Phase 8)

Target format, mean first round and count per draft:

| arm | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nQB | nRB | nWR | nTE | **nK** | nDST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 (Y1) | 2.40 | 4.18 | 1.70 | 6.44 | 7.92 | 9.96 | 1.70 | 2.12 | 4.42 | 1.92 | **3.74** | 2.10 |
| **O1-FULL** | 2.40 | 4.18 | 1.70 | 6.64 | 7.74 | **10.50** | 1.42 | **2.52** | 4.64 | **2.80** | **2.62** | 2.00 |

**The K/DST improvement survives at 10 slots and is not a small-sample artifact**: kickers drafted
**3.74 → 2.62** (D87 at 4 slots measured 3.70 → 2.60 — essentially identical). O1 does *not* take
the first kicker later (7.92 → 7.74); it stops **hoarding** them, and spends the freed picks on TE
(1.92 → 2.80) and RB (2.12 → 2.52) depth.

Early-round timing is **unchanged** — first QB, first RB, first WR identical to two decimals. All
of O1's behavioural difference is in the endgame.

**Roster legality: 0 unfilled mandatory slots in all 200 drafts, both arms, both formats.**

---

## 10. Roster utility (Phase 9)

| target format | O0 | O1-FULL | Δ |
|---|---|---|---|
| weekly (no foresight) | 1923.0 | 1973.6 | **+50.5** |
| season-long | 1963.6 | 2003.5 | +39.9 |
| **total roster points** | 2692.1 | 2672.4 | **−19.8** |
| bench contribution | 392.2 | 414.8 | +22.6 |
| missed player-weeks | 45.5 | 50.2 | +4.7 |

**O1's theoretical advantage does appear in realized weekly utility, and the mechanism is the one
claimed.** It accumulates *fewer* raw roster points (−19.8) while converting more of them into
lineup points (+50.5 weekly, +39.9 season-long) and drawing more from the bench (+22.6). It even
drafts players who miss slightly *more* time (+4.7 player-weeks) and still gains — which is what
having real depth buys.

---

## 11. RB sensitivity (Phase 6) — diagnostic only

Elite-RB cell (preseason ECR ≤ 24, n = 7) perturbed in memory; every projection-derived quantity
rebuilt. No realized outcome is an input; no production projection changed.

| Δ applied | Y1 pick #1 | O1 pick #1 | Y1 #20 | O1 #20 | Y1 #21 | O1 #21 |
|---|---|---|---|---|---|---|
| +0 | St. Brown (WR) | St. Brown (WR) | Allen (QB) | Allen (QB) | McBride (TE) | McBride (TE) |
| +25 | St. Brown | St. Brown | Allen | Allen | McBride | McBride |
| +50 | St. Brown | St. Brown | Allen | Allen | McBride | McBride |
| **+75** | **McCaffrey (RB)** | **McCaffrey (RB)** | Allen | Allen | McBride | McBride |
| +100 | McCaffrey | McCaffrey | Allen | Allen | McBride | McBride |

**O1 and Y1 have identical RB sensitivity.** Both need **+75** before taking an RB at #1; neither
changes at #20 or #21 at any perturbation up to +100.

**Weekly roster utility provides no protection against the elite-RB under-projection.** That
hypothesis is closed. (For contrast, D85's arm C lowered the #1 threshold to +50; O1 does not.)
The measured historical bias is ≈ +47.7, still short of the +75 either engine requires.

---

## 12. 2026 board (Phase 7)

| pick | Y1 (O0) | O1-FULL |
|---|---|---|
| **#1** | Amon-Ra St. Brown (WR) score 568.9 | **identical**, score 526.3 |
| **#20** | Josh Allen (QB) score 294.8 | **identical**, score 261.4 |
| **#21** | Trey McBride (TE) score 319.8 | **identical**, score 294.8 |

The top of the board is untouched. O1 lowers every score (its MSV is an availability-discounted
expectation — St. Brown's MSV 278.7 → 243.8) but preserves the ordering; `vorp` is identical by
construction because only the MSV half changed.

Final compositions, slot 1:

| arm | WR | QB | TE | RB | **K** | DST |
|---|---|---|---|---|---|---|
| Y1 | 5 | 1 | 2 | 2 | **4** | 2 |
| **O1-FULL** | 5 | 1 | **3** | **3** | **2** | 2 |

First divergence is **round 11**. Y1 drafts four kickers; O1 drafts two and spends the freed picks
on Zach Charbonnet (RB) and Hunter Henry (TE). Elite RBs, WRs, QBs, TEs and rookies at the top of
the board are unaffected.

---

## 13. Computational cost (Phase 13)

| arm | s/pick | s/draft | s per 10-slot season-format | vs Y1 |
|---|---|---|---|---|
| O0 (Y1) | **0.027** | 0.4 | 4 | 1.0× |
| O1-FULL (target) | **4.796** | 76.7 | 767 | **178×** |
| O1-FULL (legacy) | 4.445 | 71.1 | 711 | 185× |

Full experiment: 200 drafts, ≈ 2.1 h wall clock. A single live recommendation costs ≈ 5 s, which
is immaterial during a real draft.

---

## 14. Ship / do not ship

**DO NOT SHIP. Y1 remains production. No production files were changed and no production diff was
prepared**, because the pre-registered gates were not met: **G8 fails in the target format and
G3/G6/G7/G8/G9 fail in legacy.**

---

## 15. Final decision

> **"After giving O1-FULL enough sample size to actually measure its effect, do we now have
> evidence that weekly roster utility is a better objective than Y1?"**

**B — PROMISING BUT UNRESOLVED**, with the obstruction now identified exactly.

* The effect **replicated** at 2.5× the data (+52.9 → +50.5), improved **both** metrics, improved
  **4 of 5** seasons, survived leave-one-season-out, cost nothing in roster legality, and produced
  its gain through the **claimed mechanism** (fewer raw roster points, more lineup points, more
  bench contribution).
* It is **not** resolvable by this experiment, and the reason is structural: the MDE floors at
  **≈ 56 points** as slots → ∞, against an effect of **≈ 50**. **Draft slots were never the
  binding constraint; seasons are.**
* It remains a **null out of format** (legacy −2.3), which is coherent with its mechanism — that
  format has no K or DEF slots for it to act on — but which is exactly what G7 exists to flag.

**What prevents resolution:** five season clusters with a between-season SD of 45.1. One further
season (2020) is available, which would bring MDE to ≈ 47.3 against an effect of ≈ 50.5 — a
~3-point margin. That is the only remaining route on this benchmark, and it is a coin-flip rather
than a resolution.

---

## 16. Most important next research question

**Not another objective, and not more slots.** Two options, in order of value:

1. **Add 2020 and re-run (6 seasons × 10 slots).** ~2.5 h. It is the only configuration that can
   put the MDE below the effect, and it is available today. Pre-register before running, since a
   3-point margin invites post-hoc reading.
2. **If that does not resolve it, the benchmark is exhausted for effects of this size, and the
   honest move is to change the instrument rather than the candidate** — e.g. a paired variance-
   reduction design (common opponents *and* common boards across arms is already done; the
   remaining variance is genuine season-to-season football), or accept O1 as a
   theoretically-better-specified objective that cannot be empirically separated from Y1 at n=6.

**Explicitly not recommended:** shortlists (D87), further value-base reformulations (D85, nine
failures), projection work (D79–D83), or any new term.

---

## 17. Plain-English trust assessment

Nothing about Alpha's advice at the top of a 2026 draft changes. O1 makes the **identical** picks
at #1, #20 and #21, and identical first-QB/RB/WR rounds across 100 historical drafts.

What O1 changes is the **endgame**, and it changes it in the direction that makes economic sense:
Y1 drafts **3.74 kickers per draft** and O1 drafts **2.62**, spending the difference on tight-end
and running-back depth. On the 2026 board that is four kickers versus two. Across 100 target-format
drafts that behaviour is worth about **+50 realized weekly points** — real, replicated, in the
right direction on both metrics, and still inside the noise band of a five-season benchmark.

So the practical advice is unchanged from D86 and is now measured at 2.5× the sample: **take the
kicker you need, then stop.** You do not need this code change to act on it.

And the honest limit: after three phases and 340 drafts, O1 is a better-specified objective that
this benchmark **cannot** certify as a better one. That is a statement about the instrument, not
about the idea.
