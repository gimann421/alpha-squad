# W1.1 — Does a usable historical FantasyPros FLEX ECR benchmark exist?

**Status: RESOLVED. W1's finding was wrong about FantasyPros and right about the mirror.**

This phase re-opened W1's claim that *"no 1-QB weekly overall/FLEX board exists"* at the
instruction that it be treated as unresolved. It was. The correction is not a footnote: it
changes what the FLEX benchmark *is*, and the corrected data is what W2 was run against.

*Audit and acquisition only. No production change.*

---

## 1. The plain-English answer

> **Yes — FantasyPros publishes a genuine weekly RB/WR/TE FLEX consensus ranking, it is
> available historically for every week of 2021–2025, and it exists in Full PPR, Half PPR and
> Standard. W1 missed it because W1 only ever looked at one source: the DynastyProcess mirror,
> which does not carry that page.**
>
> **But our API key cannot deliver it at depth.** The configured FantasyPros key is a public
> tier that returns the **top 10 rows of any board** and nothing more, on every endpoint. So
> the real FLEX board is usable as a *top-10 benchmark and as a validator*, not as the
> full-depth benchmark W2 needed.

---

## 2. Was W1's finding correct? — a direct verdict

| W1 statement | verdict |
|---|---|
| "No 1-QB weekly overall/FLEX board exists" | **INCORRECT as written.** It is true only of the DynastyProcess mirror, and W1 stated it as a fact about the historical record. |
| "`ppr-flex.php` appears in the mirror only 2019-12-27 → 2020-10-12 and never again" | **CORRECT.** Re-verified exhaustively: 54 distinct modern `fp_page` values in the mirror, **none** an RB/WR/TE weekly board. |
| "The only weekly cross-position board *in the mirror* is the superflex one" | **CORRECT.** |
| "No Half-PPR ECR exists historically" | **INCORRECT as written.** Same error: no half-PPR page is *mirrored*; FantasyPros serves `scoring=HALF` historically for every board. |
| The FLEX reconstruction (superflex minus QBs) is a reasonable proxy | **CORRECT, and now measured against the real thing** rather than assumed — §6. |

**Root cause.** W1 audited *the source the repository already read*, and reported the limits of
that source as limits of the world. The FantasyPros API adapter existed in
`sources/fantasypros.py`, the key was configured, and D36/D37 had already recorded the API as
live — but nothing had ever queried it for weekly rankings, and W1 did not try. The lesson is
narrower and more useful than "search harder": **an audit that finds an absence must name which
source the absence is in.** W1's own §4 header said "the ECR benchmark: what exists, exactly"
and then described one mirror.

---

## 3. What was searched, and what was found

**Mirror (DynastyProcess `db_fpecr`), re-verified.** Every distinct `fp_page` in the modern era
(≥ 2020-10-16) enumerated and its position mix computed. 54 pages. The weekly family is
`qb.php`, `ppr-rb.php`, `ppr-wr.php`, `ppr-te.php`, `k.php`, `dst.php`, `ppr-superflex.php`,
plus IDP pages. No `ppr-flex.php`, no `half-point-ppr-*`, no standard-scoring page. Confirmed.

**FantasyPros API (`api.fantasypros.com/public/v2`), newly queried.** The OpenAPI spec declares
what the mirror hides:

- `position` enum contains **`FLX`** *and* **`OP`** as separate values — the regular FLEX board
  and the superflex board are distinct products.
- `scoring` enum is **`STD` | `PPR` | `HALF`**.
- `week` is a first-class query parameter; `type=WEEKLY` selects the weekly product.
- responses carry **`last_updated` / `last_updated_ts`** — a real vintage timestamp.

Verified against live historical calls, not just the spec:

| check | result |
|---|---|
| Does `FLX` return RB/WR/TE only? | **Yes** — zero QB rows on every board inspected |
| Historical depth | 2021 wk1 → 2025, every week queried returned a populated board |
| Board sizes | 310–458 players (FLX), e.g. 2023 wk8 = 371 |
| Expert counts | 43–183 experts per board |
| Half-PPR | `scoring=HALF` returns a populated, *different* board (2023 wk8: 367 vs 371 players) |
| All six positions | QB 72, RB 110, WR 166, TE 95, K 35, DST 32 (2023 wk8) — all present |

---

## 4. The vintage — and why it is better-defined than the mirror's

Every weekly board's `last_updated_ts` lands at **Sunday 12:54–13:00 ET**, with clockwork
consistency across five seasons and across the daylight-saving shift. Example, 2021 FLX PPR:

    wk1  2021-09-12 12:59 ET     wk9   2021-11-07 12:59 ET
    wk5  2021-10-10 12:59 ET     wk13  2021-12-05 13:00 ET
    wk8  2021-10-31 12:59 ET     wk17  2022-01-02 12:59 ET

That is the board **frozen one minute before the 1 PM ET kickoff**. It is a sharper and more
product-relevant cutoff than the mirror's Friday scrape — it is the last ranking a user could
actually have acted on — and it is *not the same information set*. The two sources are
**two different vintages of the same product** and are never pooled:

| | mirror (`db_fpecr`) | FantasyPros API |
|---|---|---|
| board | superflex, **reconstruction** needed for FLEX | the **real** FLEX board |
| vintage | **Friday**, post-TNF | **Sunday ~12:59 ET**, frozen at kickoff |
| depth | full (300–450 rows) | **top 10 only** |
| coverage | 79 weeks (2021–2025) | every week queried; quota-limited in practice |
| scoring | PPR only | PPR, HALF, STD |

A Sunday-12:59 cutoff still sits **after** Thursday night football and after any Sunday 9:30 AM
London game, so the already-played exclusion rule is still required — and would need widening
for the London slate if the API vintage ever became the primary benchmark.

---

## 5. Two acquisition limits, both reported rather than worked around

**5.1 A hard 10-row cap.** Every response carries `public_api_limited: true` and `limit: 10`.
`count` reports the true board size, but only ten rows are returned. Tested and defeated by
nothing: `limit=500`, `limit=0`, `offset=10`, `experts=show` all return 10. The non-public
`/v2/` and `/v1/` paths return **403**. The cap is **account-wide across every endpoint** —
`consensus-rankings`, `rankings`, `projections`, `players`, `injuries` all return 10.

**5.2 A request quota.** After roughly 120 calls the API began returning
`429 {"message":"Limit Exceeded"}` and continued to after extended backoff. The harvest was
stopped rather than pushed through; what it had already captured is what W1.1 and W2 use.

**These are access controls on a paid third-party API and were not circumvented.** FantasyPros
web pages embed fuller ranking payloads; scraping them to defeat a tier limit would be
bypassing an access control, which CLAUDE.md prohibits outright. No page was scraped.

**What this means practically:** obtaining the full-depth, real FLEX board — and a genuine
full-depth Half-PPR benchmark — is a **licensing decision, not a research problem**. A higher
FantasyPros tier would supply both immediately, against code that already exists
(`scripts/research/w11_fantasypros_flex_harvest.py`).

---

## 6. A trap that would have corrupted the study

**Per-player context in the API payload is not historical.** On the 2021 week-5 board the API
reports Davante Adams on **LAR**, Stefon Diggs on **WAS**, Cooper Kupp on **SEA**, Derrick
Henry on **BAL**, Tyreek Hill as **FA** — their *current* teams. `player_opponent`,
`player_game_kickoff_ts`, `player_game_status` and `player_bye_week` are the **historical
week's schedule joined to the current team**: internally consistent and externally wrong.

Using `player_game_kickoff_ts` for the already-played exclusion — the obvious thing to do,
since it is right there and looks authoritative — would have excluded the wrong players in
nearly every week. The design rule this forces is recorded in `benchmark.py` and pinned by
test: **take only the ranking and the player identity from a ranking source; take every
schedule and roster fact from nflverse.**

Only `player_id`, `player_name`, `player_position_id`, `sportsdata_id` and the `rank_*` columns
are retained by the harvester.

---

## 7. Is the reconstruction any good? — measured, not assumed

The pre-registered check (amendment A1, threshold **0.70 fixed before measuring**): does the
mirror's reconstructed FLEX top-10 match the real FantasyPros FLEX top-10?

| | |
|---|---|
| weeks with both | **19** (2021 wk1–17, 2023 wk8, 2024 wk5) |
| **median top-10 overlap** | **0.80** |
| mean / min / max | 0.85 / **0.70** / 1.00 |
| threshold | 0.70 |
| **verdict** | **`reconstruction_sound`** |

Every week met or exceeded the threshold; the worst week was exactly 0.70.

**This is a lower bound on reconstruction fidelity, not an estimate of it**, because the
comparison contains two differences at once: the reconstruction (superflex minus QBs vs the
real FLEX board) *and* a two-day vintage gap (Friday vs Sunday). Both push overlap down.

**One week isolates the reconstruction alone.** For 2023 wk8 the API served `FLX` and `OP` at
the *identical* vintage (`last_updated_ts` 1698598801 on both). Five of the OP top-10 were QBs;
**all five non-QB players in the OP top-10 appear in the real FLX top-10**, in near-identical
order. At the very top of the board, dropping QBs from the superflex board reproduces the real
FLEX board essentially exactly. One week is a sanity bound, not an estimate — but it points the
same way as the 19-week result.

---

## 8. Half-PPR — corrected, and a caution

FantasyPros serves `scoring=HALF` historically for every position and for FLEX. W1's "no
Half-PPR ECR exists" is **wrong**; the correct statement is **"exists, not accessible at depth
on this tier"**.

And it matters more than it might appear. At the *same* week and the *same* vintage
(2023 wk8), the FLX PPR top-10 and the FLX HALF top-10 **share only 7 of 10 names**. Three of
ten differ on scoring format alone. So a full-PPR board is **not** a usable stand-in for a
half-PPR benchmark, and W2 does not treat it as one: its half-PPR figures are explicitly
labelled "full-PPR-ranked board scored against half-PPR outcomes", never "the half-PPR ECR
benchmark". No Half-PPR ECR is approximated from Full-PPR anywhere.

---

## 9. What changed in W1 as a result

`docs/weekly/W1_FOUNDATION_AUDIT.md` carries a correction banner and its §3.2, §3.3 and §4.5
are amended in place. The three-item "things the historical record cannot give" list is now:

1. **Daily Tue–Sun cadence** — still cannot be reconstructed. **Unchanged**, and now with a
   second supporting fact: the API's own vintage is a single Sunday freeze, so it does not
   supply intermediate vintages either.
2. **Half-PPR benchmark** — **downgraded** from "does not exist" to "exists; not accessible at
   depth on the configured tier". A licensing limit.
3. **1-QB weekly FLEX board** — **retracted**. It exists. The mirror lacks it; FantasyPros has
   it; the reconstruction W1 built as a workaround has now been validated against it at 0.80
   median top-10 overlap.

---

## 10. Reproducing this audit

```bash
# mirror re-verification (offline once ingested)
uv run python scripts/research/w1_weekly_foundation_audit.py --from-db

# FantasyPros API harvest (needs FANTASYPROS_API_KEY; quota-limited)
uv run python scripts/research/w11_fantasypros_flex_harvest.py \
    --seasons 2021,2022,2023,2024,2025 --weeks 1-18 --positions FLX --scorings PPR

# the reconstruction validation runs inside the W2 benchmark
uv run python scripts/research/w2_ecr_benchmark.py --out reports/weekly/w2_results.json
```

Cached API responses live under `reports/weekly/fp_api_cache/` with a `content_sha256` per
board, so a later re-harvest can be diffed against this vintage rather than silently replacing
it.
