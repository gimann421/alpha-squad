# Draft objective modes: Maximum Value and Expert Draft

Two distinct optimization objectives for the 1-QB redraft draft engine, what each one means
precisely, and how each is measured. This document defines the objectives; it does not
implement them. Implementation sequencing lives in `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`.

Companions: `docs/TARGET_FORMAT_1QB.md` (the league), `docs/BENCHMARK_SPEC.md` (benchmark
mechanics and the standing gates), `docs/DRAFT_STRATEGY_FORENSIC_ANALYSIS.md` (why this
document exists).

---

## 1. Why two modes

The product's stated objective is to maximize realized starter points subject to a feasible
roster. Taken literally and alone, that objective has three properties worth naming:

1. **It is indifferent to bench quality.** Starter points are computed on the best legal
   lineup of season-total realized points. A bench player contributes exactly zero unless he
   out-scores a starter at his own position. Measured consequence: shipping marginal starter
   value (D60) raised starter points 1927.8 → 1990.9 while *dropping* total roster points
   2785.4 → 2455.0. The engine correctly optimized the stated metric by trading away 330
   points of bench depth.
2. **It is indifferent to within-season risk.** The metric is a season-total oracle allocation
   (`docs/BENCHMARK_SPEC.md` §4 states this). It never models a bye week, an injury, or a
   start/sit decision. A roster with no viable backup at a position scores identically to one
   with a good backup, provided the starter stayed healthy — which, in hindsight data, he did.
3. **It is measured on 5 seasons × 10 correlated draft slots.** The honest independent unit is
   the season (n=5). A mechanism that wins the pooled mean by tuning against these particular
   five seasons is not distinguishable from one that generalizes.

Mode A accepts all three properties and optimizes the metric as written. Mode B treats (1) and
(2) as real costs the metric fails to charge, and asks the engine to price them — but *only*
where the data supports a price, never by convention.

**Neither mode is defined as "looks like consensus."** Consensus is a market-information
signal and a benchmark, not a target. §4 is explicit about what is and is not admissible as an
"expert-like" criterion.

---

## 2. Mode A — Maximum Value

### Objective

> Maximize expected realized starter fantasy points, subject only to constraints that are
> genuine properties of the league configuration.

### Admissible constraints

Only these. Each is a rule of the league, not a preference:

- **Lineup legality.** The roster must be able to field the configured starting lineup:
  QB1/RB2/WR2/TE1/FLEX2(RB,WR,TE)/K1/DEF1.
- **Roster size.** Exactly `roster_size` picks (16), one per round.
- **Positional eligibility.** A position may only fill slots it is eligible for
  (`league/context.py::FLEX_ELIGIBILITY`, `SLOT_POSITION_ALIASES`).
- **Availability.** A player already drafted cannot be drafted.

### Explicitly NOT constraints in Mode A

- No positional count targets ("draft exactly 2 QBs", "at least 4 RBs").
- No hardcoded positional caps beyond what lineup legality plus roster size imply.
- No "this looks unusual" penalty. If the optimal roster is 1 QB / 7 WR / 3 RB / 2 TE / 1 K /
  1 DEF *and the model supports it*, that is the answer.
- No imitation of consensus ordering.

The existing `positional_feasibility_cap` (currently a 0.1× soft penalty, `league/roster.py`)
is **not** admissible in Mode A as presently derived: its bench-share term is a
proportional-allocation heuristic, not a legality constraint. Mode A should use the legality
floor only — a position's cap is the number of slots it could start in, plus whatever bench
the roster-size budget allows, with no proportional shaping. Whether the current cap helps or
hurts is a measurable question and is listed as an experiment in the next-phase plan.

### Metrics

| rank | metric | why |
|---|---|---|
| **Primary** | mean realized starter points | the objective, stated directly |
| S1 | win rate vs the fair benchmark opponent, per (season, slot) | distinguishes a broad edge from one big season |
| S2 | per-season mean delta, all 5 seasons shown | `docs/BENCHMARK_SPEC.md` §5: "a result from one season or one slot is not a result" |
| S3 | starter-points stdev and minimum across the 50 trials | floor and spread; Alpha's real current strength (158.9 vs consensus 214.5) |
| S4 | `n_infeasible_rosters`, `zero_drafted_starting_positions` | must be 0; a lineup that cannot be fielded is not a valid answer |

### Gates (a change failing any of these does not ship, whatever the primary metric says)

- No starting-requirement position zeroed at a higher rate than the control.
- Zero infeasible rosters.
- Determinism: two separate-process runs byte-identical, `PYTHONHASHSEED` unset.
- No leakage: every input strictly precedes the decision it informs.

---

## 3. Mode B — Expert Draft

### Objective

> Maximize realized starter points **net of the costs the primary metric does not charge** —
> specifically bench replacement value and within-season availability risk — where and only
> where those costs can be quantified from data we actually have.

Mode B is not "Mode A plus manners." It is Mode A against a **less naive scoring function**.
Every difference from Mode A must be traceable to a real cost that the season-total oracle
metric omits.

### The three admissible sources of an "expert-like" criterion

The directive forbids defining expert behavior as convention. Three sources are admissible;
everything else is not.

**(a) League structure.** Anything derivable from the configuration itself, with no appeal to
what humans do. Example: in a 1-QB league exactly one QB starts, so the marginal value of a
second QB is bounded by the probability the first is unavailable — a structural fact, not a
custom. `startable_slots()` and `FLEX_ELIGIBILITY` already encode this layer.

**(b) Measured historical outcome distributions.** Real realized data we hold, 2015–2025.
Examples that are computable today:
- Positional replacement curves — how fast realized points decay from the 1st to the Nth
  player at each position. Already partially measured: K best-minus-10th is 22–53 points,
  DST 42–44, while RB/WR curves are far steeper. This is what justifies late K/DST *on
  evidence*, not because "everyone waits on kickers."
- Games-missed distributions by position, from `player_week_stats`, giving a real, empirical
  price for backup depth instead of an assumed one.
- Realized-vs-projected residual dispersion by position and by projection tier, giving a real
  risk term. The RB residual finding (+45.2 mean overperformance, n=206) is an early,
  engine-confounded instance of exactly this.

**(c) Demonstrable performance.** A behavior qualifies as expert-like if it measurably improves
a Mode B metric out-of-sample. This is the fallback when (a) and (b) are silent, and it is
strictly evidence, never assertion.

### Explicitly NOT admissible

- "Humans usually draft RB early, so weight RB early." Convention is not evidence.
- Any positional count target or hardcoded cap chosen to make a roster look normal.
- Matching consensus's positional ordering as an objective or a regularizer.
- A penalty on any roster shape purely because it is unusual.

If a roster shape is genuinely worse, one of (a)/(b)/(c) will show it. If none of them does,
the shape is not actually a problem and Mode B should not punish it.

### Metrics

Everything in Mode A, plus:

| metric | definition | source of legitimacy |
|---|---|---|
| **Bench replacement value** | for each starting slot, the realized points of the best bench player eligible for it; summed | (a) structure — measures the roster's ability to field a legal lineup if a starter is unavailable |
| **Availability-adjusted starter points** | starter points recomputed with each starter's real games-missed applied, backfilling from the actual bench | (b) real `player_week_stats` games-played data; charges the risk the oracle metric ignores |
| **Positional timing efficiency** | for each position, (realized points of the player taken) − (realized points of the best player at that position still available at the team's *next* pick) | (b) measures whether a pick was made a round too early, entirely from realized outcomes — no convention |
| **Concentration** | Herfindahl index over drafted position shares (already in `roster_feasibility_metrics`) | reported, not optimized — a diagnostic, not a target |

**Availability-adjusted starter points is the metric that most distinguishes Mode B**, and it
is computable from data already ingested: `player_week_stats` gives real per-week
participation for 2015–2025. This replaces "expert drafters carry backups" (convention) with
"backups were worth N points in the real seasons we can measure" (evidence).

### The tradeoff to quantify

The whole point of running both modes is to answer, with numbers:

1. How many starter points does Mode B give up relative to Mode A on the raw primary metric?
2. How many does it gain back on availability-adjusted starter points?
3. Is Mode B more consistent — lower stdev, higher floor, fewer catastrophic drafts?
4. Does Mode B generalize better season-to-season (the leave-one-season-out test in the plan)?

If Mode B loses on (1) and gains nothing on (2)–(4), Mode B is not justified and Mode A ships
as the default. That outcome is permitted and must be reported if it occurs.

---

## 4. Default and exposure

Target end state, per the directive: **Expert Draft is the user-facing default; Maximum Value
is retained as an analytical mode.** That default is provisional on Mode B actually earning it
under §3's tradeoff analysis — it is a product intent, not a measured conclusion, and this
document does not pretend otherwise.

Mechanically, the mode is a property of the *decision function*, not the league, so it belongs
as an explicit parameter on `recommend_draft_pick` with a documented default — not as a global
setting and not inferred from the league config.

---

## 5. What both modes share

- The same projections (`load_season_projections`), the same market series resolution
  (`market/series.py`), the same league context.
- The same benchmark harness and the same fair opponent.
- The same pre-registration discipline: the decision rule is committed to source before any
  run against real data (D39/D54/D55 precedent).
- The same standing gates in §2.

Neither mode is allowed to use information unavailable at the moment of the pick. Both are
evaluated on realized outcomes the engine could not have seen.
