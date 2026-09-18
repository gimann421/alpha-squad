# D111 — Risk multiplier audit and ablation

Diagnostic phase. No production change, no retraining, no new feature, no change to the scoring
formula, no PR, nothing merged. `models/` `73b408e9`, `league/` `d4cfd00e`, unchanged.
Window 2021–2025. Vintage `d2955868…` (the D109 rebuild), the same board D110 ran against.

---

## Pre-registration of the Part 5 ablation

**Committed before the ablation ran.** Parts 1–4 are diagnostics and their results were known when
this was written — that is the order the phase brief specifies. What is fixed here is the ablation's
design, its metrics and its guards, none of which may be re-selected after seeing an arm result.

### The arm

    risk_mult = 1.0     for every evaluable candidate

and nothing else. Same Y1 projections, same board, same marginal starter value, same draft-aware
VORP, same opportunity cost, same roster fit, same survival, same capacity cap, same opponent
field, same seasons, same continuation. The risk formula is not altered in any other way; it is
removed from the product.

### How it is applied without touching production code

`league/draft.py` computes `risk_mult = confidence if confidence is not None else 0.7`, reading
`confidence` from `uncertainty_predictions` by `(player_id, season, model_version)`. Setting that
column to 1.0 in an isolated database copy therefore yields `risk_mult == 1.0` exactly.

**The complication this design must handle.** About a quarter of the projection universe has no
uncertainty row at all — every DST (32/season), most kickers (~44/season) and ~100 rookies — and
those candidates take the hardcoded **0.7** fallback instead of a model output. Setting only the
existing rows to 1.0 would not ablate risk; it would silently re-weight skill players against
K/DST/rookies. The ablation therefore also **inserts** a row for each projection-universe player
that lacks one, carrying that player's exact projection and position, so that
`load_season_projections` returns a byte-identical board while `_confidence_for` returns 1.0 for
everyone.

**Two guards, which abort the run rather than report:**

1. the assembled `board_hash` for every season is **unchanged** from control — proving the
   projections did not move, so this is an ablation of risk alone; and
2. every player in the projection universe returns `confidence == 1.0`.

### Metrics

**Primary:** whole-draft realized starter points, per `(season, slot)`, differenced against control
on the same `(season, slot)`. Inference unit is the **season cluster** (n=5, t(4) = 2.776), per
D88's finding that the detection floor is bound by seasons and slots cannot lower it.

**Secondary / diagnostic, never primary:** weekly realized value under
`draft_oracle.py::WEEKLY_NO_FORESIGHT`; a cross-format run on `legacy_2qb_dynasty`, the repo's
designated second format; rounds 1–3 realized value; positional composition and first-RB round.

**Explicitly not primary:** arm-relative pick regret (D105/D106 — it goes non-monotone when the arm
changes the oracle comparison), and the number of decisions changed. *Drafting more RBs is not a
result.* Only realized draft value decides the primary conclusion.

### Population and power

Target format: 5 seasons × 10 slots = **50 paired drafts** per arm (D110 ran 4 slots; D111 has only
two arms, so the full slate is affordable and is used). Cross-format: 5 seasons × 4 slots.
Power is re-derived empirically on this vintage and reported against D109's ≈177 points/draft
reference, with the result stated as powered or underpowered **before** the null is interpreted.

### Pre-committed interpretation rule

A result counts as a real effect only if the season-cluster 95% interval excludes zero. If it does
not, the phase reports the effect as undetected and states whether the experiment had the power to
have seen ~177 points/draft. No replacement risk formula is selected in this phase under any
outcome; Part 9 is diagnostic only.

Runners: `scripts/research/d111_risk_audit.py`, `d111_risk_leverage.py`, `d111_ablation.py`,
committed before the ablation ran.
