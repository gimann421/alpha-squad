# D110 — Cross-position magnitude sensitivity

**Status at this commit: PRE-REGISTRATION ONLY. No arm has been run.** Results are appended to
this document in a later commit; nothing below may be changed once an arm result has been seen.

Diagnostic/sensitivity experiment. No production change, no retraining, no new feature, no
calibration, no change to the scoring formula, no PR, nothing merged.

## The question

Not *"can we build a better projection model"*, but:

> **Is cross-position projection magnitude actually a causal lever in Alpha's early-round
> decisions, and is the effect large enough to matter in realized draft value?**

D109 established that Alpha is WR/QB-heavy in rounds 1–3 and delays RB; that Y1 has a real
cross-position magnitude defect concentrated at the RB upper tail; and that individual picks are
often robust to the observed error while the *aggregate* early-round construction is sensitive at
roughly the magnitude of that error. This phase isolates that axis before any calibration method
is considered.

## Frozen

Y1 model weights, the production decision engine (`league/`), board construction, draft format
(10-team 1-QB PPR, `roster_size` 16), the continuation/opponent policy, the seasons (2021–2025),
and all production code. Nothing is retrained. Nothing is tuned against realized outcomes.

## The transformation

    adjusted_projection = position_multiplier × Y1_projection

A strictly positive multiplier is monotone, so **within-position order is preserved exactly**;
only the magnitude of one position relative to the others moves. This is deliberately *not*
quantile calibration, isotonic regression, Platt scaling, empirical Bayes, or any learned map.

Applied in an isolated database copy to **both** projection tables the engine's own loader reads:
`uncertainty_predictions.point_prediction` and `rookie_predictions.predicted_rookie_points`
(rookies are 143 of 714 RBs in this window, so scaling only the former would leave a fifth of the
position unscaled). Verified per position per season against `load_season_projections` before any
draft runs — D81 recorded that an override passed as an argument is a silent no-op.

**`confidence` is never touched**, so the engine's `risk` multiplier is byte-identical across
arms. D109 flagged risk as a suspect; holding it frozen keeps it a control here rather than a
confound. It is examined separately, as a diagnostic only.

Opponents draft by ECR, which no arm touches, so every arm faces an identical opponent field on
an identical board: trials are paired by `(season, slot)`.

## The grid (frozen before any result was seen)

Centred on Y1 = 1.00 and deliberately **coarse**. D109's implied RB correction is ≈ **×1.21**
(a −41.5 point bias on a mean projection of 197.1 inside ECR ≤ 30); the grid brackets that
generously in **both** directions. No direction is assumed correct.

**Value-scored arms** — 5 seasons × 10 slots = 50 paired drafts each:

| arm | multipliers | purpose |
|---|---|---|
| `control` | all 1.00 | frozen Y1 |
| `rb_080`, `rb_090` | RB 0.80 / 0.90 | RB magnitude **down** |
| `rb_110`, `rb_120` | RB 1.10 / 1.20 | RB magnitude **up**, bracketing the implied ×1.21 |
| `rb_140` | RB 1.40 | far beyond any measured bias — does *any* magnitude help? |
| `qb_090`, `qb_110` | QB 0.90 / 1.10 | move QB instead of RB |
| `wr_090` | WR 0.90 | move WR instead of RB |
| `gap_rb120_wr090` | RB 1.20 + WR 0.90 | the D109-implied **gap** correction |

**Decision-surface-only arms** — 5 seasons × 4 slots (1, 4, 7, 10; the repo's own `DEFAULT_SLOTS`
from D103). Reported *only* as threshold resolution for Part 2, **never** as a value comparison:
`rb_095`, `rb_105`, `rb_115`, `rb_130`.

**Exclusion, stated in advance.** TE gets no arm: D109's TE bias (−17.0) rests on n=8 inside
ECR ≤ 30, and TE is taken in only 10 of 150 early picks, so a TE arm would buy threshold
resolution on a cell too small to interpret. A scope decision, not a finding.

## Metrics

**Primary:** absolute realized starter points of the full 16-round roster, per `(season, slot)`,
differenced against the control on the **same** `(season, slot)`.

**Explicitly not primary:** arm-relative pick regret. D105/D106 established it becomes
non-monotone once the arm itself changes the oracle comparison, and D106's matched regret ladder
self-invalidated for exactly that reason.

**Secondary/diagnostic:** rounds 1–3 vs 4–6 vs full-draft realized value (diagnostic only — the
whole-draft objective remains the north star); positional attribution of any value difference;
and a power check re-derived on this vintage against D109's ≈ +177 points/draft expectation.

## Instrument

`evaluation/draft_simulation.py::simulate_draft` with `ALPHA_LEAGUE_AWARE` — which calls
`league/draft.py::recommend_draft_pick` itself — against the fair roster-aware consensus opponent
field (`MARKET_CONSENSUS_ROSTER_AWARE`, D61 Stage 1.1). No parallel scoring implementation exists
in this phase. Cross-instrument parity check: `simulate_draft` returns 2132.0 starter points for
2021 slot 1, byte-identical to what D109's `audit_opening` reported for the same cell.

## Data vintage

The D109 rebuild — assembled board `combined_hash`
`d2955868ccf9714bbe087c896c4cec06df44659f18b7262ad48cf484fce25c1f`. The upstream DynastyProcess
board and identity map reproduce D89 byte-identically; the **nflverse panel underneath them was
restated upstream** (D109 §0). Numbers in this phase must **not** be compared against pre-D109
published figures as if they came from identical data. The runner records the vintage on every
row.

Runner: `scripts/research/d110_magnitude_grid.py` (committed before any arm ran).
