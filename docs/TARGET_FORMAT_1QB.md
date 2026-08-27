# Target format — 10-team 1-QB redraft PPR

**Status:** current product default (docs/DECISIONS.md D58). Supersedes the 2QB dynasty
target (D7), which remains registered as `legacy_2qb_dynasty`.

This is the format Alpha Squad optimizes for by default. It is **not** a hard-coded
limitation: supplying a different league configuration selects a different lineup, different
replacement levels, different positional capacities, and a different consensus benchmark
board, with no code change. `legacy_2qb_dynasty` exists partly to prove that.

---

## Lineup

| Slot | Count | Filled by |
|---|---|---|
| QB | 1 | QB |
| RB | 2 | RB |
| WR | 2 | WR |
| TE | 1 | TE |
| FLEX | 2 | RB, WR, TE |
| K | 1 | K |
| DEF | 1 | DST |
| **Starters** | **10** | |

10 teams, PPR (1.0 per reception), snake draft, FAAB budget 100.

### Slot names vs. position names

The config (and Sleeper) name the team-defense slot `DEF`. nflverse and FantasyPros name the
position `DST`. `league/context.py::SLOT_POSITION_ALIASES` normalizes slot names into the
position vocabulary the data actually uses, so `dedicated_slots()` reports `DST`, not `DEF`.
Without this the slot would look for a position no row in the database has and would go
silently unfilled — scoring zero rather than failing loudly.

## Roster arithmetic

```
starters     10
bench         6
roster_size  16      (10 + 6)
```

`roster_size` is also the number of rounds the draft benchmark runs, so it has to be the real
total rather than an independently chosen number.

**This is a correction, not just a setting.** The pre-D58 config declared 9 starters and a
10-player bench alongside `roster_size: 17` — three numbers that could not all be true
(`docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` §3 documented the inconsistency). A test now asserts
`sum(lineup.values()) + bench == roster_size` for every shipped config, so the three cannot
drift apart again.

## Positional capacity

Capacity is **derived from the configuration**, never hardcoded per position
(`league/roster.py`):

```
startable_slots[pos]  = dedicated slots + every flex slot the position is eligible for
capacity[pos]         = startable_slots[pos] + max(1, round(bench * startable share))
```

For this format:

| | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| dedicated | 1 | 2 | 2 | 1 | 1 | 1 |
| startable (incl. FLEX) | 1 | 4 | 4 | 3 | 1 | 1 |
| **capacity (hard cap)** | **2** | **6** | **6** | **4** | **2** | **2** |

Two properties are deliberate:

- **Flex eligibility counts in full, not shared out.** A single RB can hold both FLEX spots,
  so RB's startable count is 2 + 2 = 4. The pre-D58 model ignored FLEX entirely, which made
  RB and WR look like 2-slot positions in a league that routinely starts four of them.
- **Bench is allocated proportionally, not evenly.** The pre-D58 model divided the bench
  evenly across dedicated positions. Adding K and DEF took that divisor from 4 to 6 and cut
  RB's and WR's allowance by a third, while handing kickers and defenses bench room no real
  roster uses. Every position keeps a one-slot floor, so a backup QB is never structurally
  forbidden.

These are ceilings past which one more body cannot start, not targets. **The engine does not
optimize toward a roster-count target** such as "draft exactly 2 QBs"; it optimizes realized
starter points subject to feasibility.

## Objective

> Maximize expected realized fantasy **starter** points over the season, subject to producing
> a feasible roster for the supplied league configuration.

Ultimately Alpha must **outperform** historical market consensus, not merely match it. The
evaluation hierarchy and what counts as consensus are specified in `docs/BENCHMARK_SPEC.md`.

## Data coverage for this format

| Position | Projections | Realized points | Market rank |
|---|---|---|---|
| QB / RB / WR / TE | M6 uncertainty model (+ M7 rookies) | nflverse | `ro` board |
| K | measured baseline (D57) | computed from FG/PAT components (D57) | `ro` board |
| DST | measured baseline (D57) | computed from team defensive stats + points allowed (D57) | `ro` board (D57) |

K and DST were all three absent before D57: kickers scored 0.0 because nflverse prices only
passing/rushing/receiving, and team defenses did not exist as an entity anywhere. See
`docs/DECISIONS.md` D57 and `features/kicking_defense.py` for how each is now derived from
real data, and `models/baselines/kicking_defense.py` for why both are baselines rather than
models.
