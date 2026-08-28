# Draft benchmark specification

What "market consensus" means in this project, which board is the right one for the target
format, and how a change to the draft engine is judged. Companion to
`docs/TARGET_FORMAT_1QB.md`.

---

## 1. What consensus is

The consensus opponent drafts **best available by real historical preseason ECR**, from the
board that matches the league's format.

- Source: DynastyProcess's `fp_ecr_history` mirror of FantasyPros (D3), stored in
  `market_snapshot`.
- Scoping: the latest **July/August** snapshot per player in the target season
  (`market/edge.py::_preseason_overall_market`). This is the project's canonical leakage-safe
  market pattern (D54) — a decision "as of" a draft never reads market movement that happened
  after it.
- Tie-break: `player_id`, deterministically (`league/opportunity_cost.py::best_by_market_rank`).
  Real ECR ranks tie often, and `PYTHONHASHSEED` is unset, so without this a re-run of the
  same historical draft could pick a different player among ties.

In `evaluation/draft_simulation.py`, nine of ten slots always draft this way and only the
tenth varies by strategy. That is what makes "strategy X beat strategy Y" a real comparison
rather than two runs against different unmeasured opponents.

## 2. A market series is `(ecr_type, page_type)`, not an `ecr_type`

`ecr_type` alone is **not a rank space**. DynastyProcess labels several independently-ranked
FantasyPros pages with the same `ecr_type`. Measured on the real snapshot:

| ecr_type | page_type | FantasyPros page | rows |
|---|---|---|---|
| `ro` | `redraft-overall` | `ppr-cheatsheets.php` | 102,563 |
| `ro` | `redraft-idp` | `idp-cheatsheets.php` | 38,873 |
| `rsf` | `redraft-op` | `ppr-superflex-cheatsheets.php` | 99,694 |

Reading `ro` unscoped merges the PPR draft board with a separately-ranked IDP board. The two
1..N sequences collide: in preseason 2024, `ro` rank 3.0 was simultaneously an LB and a WR.
Worse, because the pre-D56 primary key did not include the page, one of any two rows a player
held on the same date was silently dropped.

`market_snapshot.page_type` is now part of the key, and
`market/series.py::resolve_market_series` resolves the pair from the league itself.

`redraft-overall` also carries `ros-ppr-overall.php` (rest-of-season) rows — a genuinely
different product. Verified: those appear only in months 9–12, so the July/August scoping
every consumer already applies excludes them by construction.

## 3. Why `ro` and not `rsf` for this format

This is the decisive point, and it invalidates the project's entire pre-D56 draft record.

`rsf` is FantasyPros' **superflex** board. D21 chose it deliberately and correctly, because
the target league was then 2QB. It is the wrong board for a 1-QB league. Measured on the real
preseason-2024 snapshot:

| board | QBs in the overall top 15 | first QB |
|---|---|---|
| `rsf` | **9 of 15** | ECR 1.7 |
| `ro` | **0 of 15** | ECR 23.4 |

And on what a consensus draft actually builds — 10-team snake, 2021–2025 × 10 slots = 50
drafts per board, all slots picking best-available by ECR:

| board | mean QB | mean RB | mean WR | mean TE | share landing on 1–3 QBs |
|---|---|---|---|---|---|
| `rsf` | 4.1 | 5.1 | 6.1 | 1.8 | 20/50 (40%) |
| `ro` | **2.4** | 5.5 | 6.9 | 2.1 | **40/50 (80%)** |

So the common claim that a 1-QB redraft team drafts roughly 1–3 QBs **is supported by this
project's own historical consensus data under `ro`**, and is not supported under `rsf`.

`ro` also has better coverage than `rsf`: 211k rows / 3,110 players from 2019-12, against
98k / 1,393 from 2021-01, with 9–10 preseason snapshot dates in every season 2021–2025.

**Consequence to state plainly:** every draft number recorded before D56 — the 2020.7
consensus starter points, Alpha's 1801.1, the −219.6 gap, the M17 forensic audit, the D55
P-tier ablation — describes Alpha playing a *superflex* league. Those results remain valid
for the league they measured and are labelled as such; they do not transfer to the 1-QB
target, and are not restated as if they did.

### Known limitation of the consensus opponent

The consensus bot has **no roster awareness**. It picks best-available by ECR for all 16
rounds, so its late-round picks produce a 4–6 QB tail a human would never draft (visible in
the `ro` distribution above). It remains the honest available proxy — there is no distinct
historical ADP series in this environment (D17) — but the tail is a property of the opponent
model, not of real consensus behavior, and is not presented as one.

## 4. Scoring

- **Realized outcomes only**, from `player_season_stats` — never projections.
- A drafted player with no season row really did score 0 real points. That is the honest
  outcome of the pick, not a gap to paper over.
- **Starter points** are computed by re-running `compute_league_starters` over the drafted
  roster with `teams: 1`, allocating dedicated slots by within-position rank and then FLEX
  slots to the best remaining flex-eligible players — i.e. the best legal lineup that roster
  could field, by full-season totals.

**Limitation, stated rather than implied:** this is a season-total allocation. It does not
model weekly lineup decisions, byes, or in-season injury replacement. It is the same metric
for every strategy, so comparisons are fair, but it is an upper bound on what a manager would
actually have started.

## 5. Evaluation hierarchy

**Primary — the metric that decides:**

1. **Mean realized starter points.** Total roster points rewards bench hoarding, which is
   precisely the pathology under study, so it is never primary.

**Secondary — reported alongside, never traded against the primary without saying so:**

2. Win rate vs. market consensus (share of season × slot trials where Alpha beats it).
3. Total realized roster points.
4. Positional feasibility — can the roster field a legal lineup at every slot.
5. Roster concentration — the positional distribution, and how far it sits from what
   consensus builds.
6. Position-specific failure rates — e.g. how often a starting slot is left unfillable.
7. Consistency across seasons and across all 10 draft slots. **A result from one season or
   one slot is not a result.**

**Gates a change must not fail**, regardless of the primary metric:

- No position carrying a starting requirement may be zeroed at a higher rate than the control.
- Determinism: two separate-process runs must produce byte-identical reports.
- No leakage: every input strictly precedes the decision it informs.

## 6. Pre-registration

Any candidate engine change commits its decision rule **to source, before** being run against
real data (the D39/D54/D55 discipline). Improving a headline pathology is not by itself
evidence the system got better; a mechanism that fixes RB=0 while losing starter points does
not qualify.

## 7. Reproduction

```bash
uv run alpha-squad train kdst-projections            # K/DST projections (D57)
uv run alpha-squad evaluate draft-simulation \
    --season-start 2021 --season-end 2025 \
    --league-id target_league \
    --report-path reports/draft_simulation.md
```

Seasons start at 2021 because that is where real walk-forward
`uncertainty_predictions` coverage begins.
