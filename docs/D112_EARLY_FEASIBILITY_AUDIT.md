# D112 — Does Alpha actually have an early roster-feasibility problem?

**Verdict: NO. B + D — Alpha already handles feasibility, and the D111 effect is an artifact of the
benchmark.** The legality constraint is **binding in 0 of 1,600 Alpha picks** across 100 drafts in
both shipped formats. Category C — "the constraint changes the preferred candidate" — is **exactly
0**, in rounds 1–6 and everywhere else. Alpha finishes its eight mandatory slots with **5–6 picks
to spare** in 100 of 100 drafts, and **0 of 100 final rosters is illegal**.

**The D111 +241/+215 effect is fully accounted for and does not transfer.** `ECR_ALONE_NAIVE`
drafts **zero kickers and zero defenses in 40 of 40 drafts**, forfeiting both slots. Those two
slots are worth **226.0 (target) / 226.1 (dynasty)** realized starter points — which brackets the
measured +241.1 / +215.3. It is the price of an intentionally naive benchmark never ranking a K or
DST highly on an overall ECR board, not evidence of any defect in Alpha.

**No counterfactual was run.** The pre-registered stopping rule fired: a clean diagnostic that the
D111 recommendation does not apply is the deliverable.

**No production change. No `src/` change at all. No model fitted. Nothing merged. No PR.**

---

## 1. The premise, and why it needed challenging

D111 measured that giving a pure-ECR drafter the end-of-draft mandatory-slot rule is worth +241.1 /
+215.3 points, 5/5 seasons, t ≈ 14–15 — the only effect in that phase above the 172–250 detection
floor — and recommended testing whether enforcing feasibility *earlier* carries the same effect.

**That recommendation silently assumed Alpha has the problem the benchmark had.** D112 tests the
assumption before spending a counterfactual on it.

### Alpha's two roster mechanisms are different things

Conflating them is the trap this phase exists to avoid.

| | mechanism | where | in production? |
|---|---|---|---|
| **MINIMUM (legality)** | `unfilled_dedicated_slots` → restrict the pick to unfilled mandatory positions once `picks_remaining ≤ deficit` | `roster_aware_market_pick`; tiers `W2`/`W3`, `L1`/`L3` | **No** — tier `L0` does not carry it |
| **MAXIMUM (capacity)** | `positional_feasibility_cap` × `OVER_CAP_VALUE_MULTIPLIER = 0.1` once the roster holds that many | `score_candidate`, all draft-aware tiers | **Yes** |

Both shipped formats: 8 mandatory dedicated slots (QB 1, RB 2, WR 2, TE 1, K 1, DST 1), 16 rounds,
caps QB 2 / RB 6 / WR 6 / TE 4 / K 2 / DST 2.

### The quantity the audit turns on

At each of Alpha's picks,

    slack = picks_remaining − Σ unfilled_dedicated_slots(league, roster)

counting the current pick. It starts at **8**, falls by exactly 1 for a pick that does not fill a
mandatory slot, and is unchanged by one that does. **`slack == 0` is precisely when the existing
legality rule activates.** So `min(slack) > 0` over a draft ⇒ the constraint never binds there and
no earlier enforcement of it could have changed any pick. That is a deterministic identity, which
is what lets a finite audit be conclusive rather than merely suggestive.

> **A statistic I had to correct mid-phase.** My first cut quoted the *whole-draft* minimum slack,
> which came out as exactly 1 in 100/100 drafts — and that is arithmetic, not a feasibility fact:
> once the deficit reaches zero, slack is just `picks_remaining` decaying to 1 at the final pick.
> The meaningful margin is the minimum **while a mandatory slot is still outstanding**. The runner
> records both; the report quotes the live one, and a test pins the distinction.

---

## 2. Validation

| check | result |
|---|---|
| board / data vintage | `63076e2e2bbfbbe5c29fb41265966ac1b8aaa180b3e89ee7742388fcc19d98ad` — unchanged from D111 |
| **Y1 control parity** | `target_league` **2002.9** vs D111's recorded **2002.9**; `dynasty_1qb` **2061.5** vs **2061.5** — **exact**, on D111's {1, 4, 7, 10} grid |
| player pool, board, roster rules, continuation, scoring, draft settings | unchanged — the audit walks the same `_pick_by_tier` / `roster_aware_market_pick` / `compute_league_starters` path D111 used |
| `models/` / `league/` | `73b408e9…` / `d4cfd00e…`, byte-identical |

Population: 2021–2025 × **all 10 draft slots** × both formats = **100 drafts, 1,600 Alpha picks**
per… (50 drafts / 800 picks per format). The audit is a census, not a paired experiment, so every
slot is walked rather than D111's four.

**Could the detector have fired?** A negative result is worth nothing if the instrument cannot
produce a positive. `tests/unit/test_d112_feasibility_audit.py` constructs rosters at the
feasibility frontier and asserts the classifier returns **C** when the constraint changes the pick
and **D** when it agrees, that it activates at exactly `slack == 0` and not a pick earlier, and
that the `DEF` slot ↔ `DST` position alias resolves (a missing alias would make every roster look
illegal and manufacture the very problem under test).

---

## 3. Part 1 — Alpha is never at risk

| | `target_league` | `dynasty_1qb` |
|---|---|---|
| final rosters illegal | **0 / 50** | **0 / 50** |
| picks where the legality rule is **binding** | **0 / 800** | **0 / 800** |
| picks where it **changes the choice** (C) | **0 / 800** | **0 / 800** |
| min live slack (rule needs 0) | **5** (median 6) | **5** (median 5) |
| drafts where slack ever reached 0 | **0 / 50** | **0 / 50** |
| round the last mandatory slot is filled | mean 10.18, worst 11 | mean 10.62, worst 11 |
| pool supply at the scarcest outstanding slot | min **32** | min **32** |

**Alpha finishes its mandatory slots with five to six picks to spare, in every single draft.** The
second failure mode — the pool running out of a needed position — is also not live: the scarcest
outstanding mandatory position never has fewer than 32 available players (the 32 team defenses).

First round each mandatory position is filled, and the resulting composition:

| | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| target — mean first round | 2.36 | 4.44 | 1.62 | 6.30 | 8.74 | 10.18 |
| target — worst | 4 | 7 | 4 | 9 | 9 | 11 |
| target — mean count | 1.84 | 3.04 | 5.18 | 2.60 | **2.00** | 1.34 |
| dynasty — mean first round | 2.10 | 4.48 | 1.48 | 5.74 | 8.86 | 10.62 |
| dynasty — worst | 5 | 7 | 4 | 10 | 9 | 11 |
| dynasty — mean count | 1.94 | 3.10 | 5.56 | 2.34 | **2.06** | 1.00 |

**Never zero at any position, in any of the 100 drafts.** Note the direction of Alpha's actual
kicker behaviour: it drafts **2.00 / 2.06** kickers against a cap of 2 — it *over*-fills K rather
than under-filling it, which is the documented D85/D94 early-kicker pathology and the opposite of a
feasibility risk.

**Crucially, Alpha fills these slots early for *valuation* reasons, not feasibility ones** — the
legality rule is absent from `L0` and never activates. That is why feasibility never becomes
binding: the value terms get there first, with room to spare.

---

## 4. Part 2 — the early picks are not constrained at all

A = no mandatory slot outstanding · B = a constraint exists but is not binding · **C = binding and
changes the pick** · D = binding but does not change the pick.

| format | rounds | picks | A | B | **C** | D | min slack |
|---|---|---|---|---|---|---|---|
| target | **1–6** | 300 | 0 | **300** | **0** | 0 | **6** |
| target | 7–11 | 250 | 41 | 209 | **0** | 0 | 5 |
| target | 12–16 | 250 | 250 | 0 | **0** | 0 | — |
| dynasty | **1–6** | 300 | 0 | **300** | **0** | 0 | **6** |
| dynasty | 7–11 | 250 | 19 | 231 | **0** | 0 | 5 |
| dynasty | 12–16 | 250 | 250 | 0 | **0** | 0 | — |

**Every one of the 600 early picks is category B**, six picks clear of the frontier. C and D are
empty across all 1,600 picks — the rule never binds anywhere in the draft, so it never insures
against anything either.

Alpha's picks *do* fill mandatory slots naturally: 100% of rounds 1–3 in both formats, 100% of
round 9 (the kicker), falling to 0% from round 12 once everything is covered.

### The capacity ceiling — the mechanism that *is* in production

| format | rounds | cap fires | changes the pick |
|---|---|---|---|
| target | **1–6** | **0.0%** | **0.0%** |
| target | 7–11 | 3.6% | 3.2% |
| target | 12–16 | 90.0% | 38.4% |
| dynasty | **1–6** | **0.0%** | **0.0%** |
| dynasty | 7–11 | 6.4% | 0.0% |
| dynasty | 12–16 | 78.4% | 16.8% |

The un-penalised score is recovered exactly (the penalty is a pure ×0.1), so "changes the pick" is
an exact counterfactual, not an estimate. **Positional capacity does not touch a single early Alpha
decision.** It is a late-round mechanism, and where it acts it is doing its job — the swaps it
prevents are QB→TE, K→WR, QB→WR, QB→DST, i.e. stopping a third quarterback or third kicker in
rounds 12–16.

---

## 5. Part 3 — why no counterfactual was run, and why one cannot be built

The pre-registered stopping rule fired: category C is not "≈ 0%", it is **exactly 0 of 1,600**.

There is also a structural reason, which matters more than the stopping rule. The brief required a
treatment differing from control **only in when the already-existing legality constraint becomes
binding**, using the existing definitions and adding no new parameter. That cannot be built:

- The existing rule activates at `slack ≤ 0` — **by construction the last moment at which
  feasibility is still guaranteed**. It is already as early as a *legality* constraint can be
  without constraining picks that are not at risk.
- To make it bind anywhere in rounds 1–6 you would need a threshold `slack ≤ k` with **k ≥ 6**;
  to make it bind at round 1, **k ≥ 8**. At k = 8 the restriction is unconditional — "fill all
  eight mandatory slots before any other pick."
- That is a positional-balance strategy with an invented coefficient, not a legality rule. **Part 4
  of the brief rules it out explicitly**, and rightly: a legal roster is not the same thing as a
  good one, and forcing a DST in round 1 would be imposing a fantasy-football convention, not
  testing feasibility.

So the honest finding is not merely "a counterfactual was not warranted" but "**the counterfactual
D111 proposed is not definable within the existing roster-legality definitions**."

---

## 6. Part 6 — does the D111 effect transfer to Alpha?

**Answer: D, primarily — the effect is mostly an artifact of the ECR-alone benchmark — with B as
the corollary: Alpha already handles feasibility adequately.** Not A. Not C.

The decomposition is exact:

| arm | mean K per draft | mean DST per draft | drafts with **no** kicker | with **no** defense |
|---|---|---|---|---|
| `Y1` (target) | 2.00 | 1.40 | **0 / 20** | **0 / 20** |
| `ECR_ALONE` (target) | 1.00 | 1.00 | 0 / 20 | 0 / 20 |
| **`ECR_ALONE_NAIVE`** (target) | **0.00** | **0.00** | **20 / 20** | **20 / 20** |
| `Y1` (dynasty) | 2.05 | 1.00 | **0 / 20** | **0 / 20** |
| **`ECR_ALONE_NAIVE`** (dynasty) | **0.00** | **0.00** | **20 / 20** | **20 / 20** |

`ECR_ALONE_NAIVE` never drafts a kicker or a defense in any draft, because an overall ECR board
never ranks one highly enough to be best-available. It therefore forfeits both slots and scores
**0.0** in each. Those two slots are worth, measured on the roster-aware arm:

| format | realized starter points from the K + DEF slots | D111's measured contrast |
|---|---|---|
| target | **226.0** | +241.1 |
| dynasty | **226.1** | +215.3 |

**226 brackets both measured effects.** The residual is the value of the two picks the naive
drafter spent elsewhere instead — approximately zero under season-long scoring, because they land
on the bench. D67's ~−130-points-per-forfeited-starter figure predicted this within rounding.

The effect is real and correctly measured; it is simply **a property of the benchmark opponent's
documented lack of roster awareness** (`docs/BENCHMARK_SPEC.md` §3), not a transferable lesson
about Alpha. My D111 recommendation over-read it, and this phase retracts it.

---

## 7. What this phase does and does not establish

- It **does** establish that early roster feasibility does not constrain Alpha on realistic boards
  in either shipped format, 2021–2025 — 0 of 1,600 picks, with 5–6 picks of margin.
- It **does** establish that the D111 +241/+215 is the two forfeited starting slots.
- It **does not** say Alpha's roster construction is optimal. Legality is not quality (Part 4). The
  K = 2.00/2.06 behaviour against a cap of 2 remains the open pathology D85/D94 documented, and it
  is a *capacity* question, not a feasibility one.
- It **does not** generalise beyond these two 1-QB formats, these seasons and this board. A
  shallower roster, a deeper mandatory lineup, or a format with more required slots than
  `roster_size` allows slack for could bind where this one does not — the audit is cheap to re-run
  if a format changes.
- It **does not** touch ECR, risk or projections. The frozen risk/uncertainty question from D111
  remains open and untouched.

---

## 8. Reproduction

```
uv run python scripts/research/d112_feasibility_audit.py --mode parity --out <dir>
uv run python scripts/research/d112_feasibility_audit.py --mode audit  --out <dir>
uv run pytest tests/unit/test_d112_feasibility_audit.py
# board vintage: 63076e2e2bbfbbe5c29fb41265966ac1b8aaa180b3e89ee7742388fcc19d98ad
```

Artifacts in `docs/d112_artifacts/`: the full audit report, the parity result, and the per-draft
summary JSON. The per-pick JSON (1,600 rows) regenerates deterministically from the command above.
