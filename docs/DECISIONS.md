# Decisions Log

Durable record of assumptions and resolutions made while executing
`CLAUDE_CODE_LEAD_PROMPT.md`. Append-only; do not delete superseded entries — mark them
superseded instead.

## D1 — Original v1 documents absent
`CLAUDE_CODE_LEAD_PROMPT.md` §1 references `fantasy_football_ml_ai_model_spec_v1.md` and three
sibling documents. They are not present in the repository. The consolidated package
(`PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE_CRITERIA.md`,
`AGENT_CONTRACTS.md`) is treated as authoritative, per `README.md`: "The consolidated package
resolves implementation-workflow conflicts... while preserving product requirements."

## D2 — Python 3.12
`ARCHITECTURE.md` §14 requires Python 3.12+. The environment default is 3.11.15, but
`/usr/bin/python3.12` (3.12.3) is present. Project pins `>=3.12` and uses `uv` to select it.

## D3 — Verified data-source reachability (2026-08-20)
Probed directly rather than assumed, per lead prompt §4. Full table in `docs/DATA_SOURCES.md`.
Summary: nflverse, DynastyProcess (FantasyPros ECR history/current + dynasty values + ID
crosswalk), cfbfastR-data (college production), ffopportunity (expected fantasy points) are all
reachable over HTTPS via `raw.githubusercontent.com` / GitHub release assets. Direct calls to
`api.sleeper.app`, `api.collegefootballdata.com`, `api.fantasypros.com`, `keeptradecut.com`, and
`site.api.espn.com` return `403` at the environment's egress proxy (policy denial, confirmed via
`/root/.ccr/__agentproxy/status` — `connect_rejected`, not an auth failure).

**Resolution:** implement adapters for the blocked sources exactly as specified (same request
shape, same schema mapping) so they activate unchanged if the policy or credentials change. Until
then they raise and register `BLOCKED_BY_POLICY` in the source health registry — never return
fabricated or empty-but-silent data. Use the verified open substitutes as the operating data path:

| Spec source | Blocked transport | Verified substitute in use |
|---|---|---|
| FantasyPros ECR/ADP | `api.fantasypros.com` | DynastyProcess `db_fpecr.parquet` (historical, `scrape_date`) + `values-players.csv` (current, includes `ecr_2qb`) |
| Sleeper | `api.sleeper.app` | DynastyProcess `db_playerids.csv` for `sleeper_id` crosswalk; league state itself loaded from local YAML (see D6) |
| CollegeFootballData | `api.collegefootballdata.com` | cfbfastR-data `player_stats_{season}.parquet` |
| KeepTradeCut | `keeptradecut.com` | DynastyProcess `values-players.csv` / `values-picks.csv` (dynasty value, distinct signal from ECR) |
| ESPN | `site.api.espn.com` | Not substituted; not a core required source. Marked BLOCKED, unused by v1. |

This is not a product simplification: the same underlying signals (consensus ECR, dynasty market
value, college production, ID crosswalks) are present, sourced from the data providers' own open
distributions rather than blocked JSON APIs.

## D4 — Per-expert accuracy weighting: LIMITED
`PRODUCT_SPEC.md` calls for "expert rankings weighted by demonstrated accuracy." Only FantasyPros
*consensus* ECR (best/worst/average across anonymized experts) is reachable; individual expert
identity requires the blocked FantasyPros API. Weighting is implemented at the *source* level
(consensus ECR vs. dynasty market value vs. model) instead of per-expert. Marked LIMITED in
`docs/TRACEABILITY.md` with this reason; the per-expert path is not deleted, just unreachable.

## D5 — Free-text news evidence: LIMITED
No news/social API is reachable in this environment. `news_evidence` evidence events are derived
from structured official signals already ingested: depth-chart rank deltas, injury-report status
transitions, roster transactions, and week-over-week snap/route/target share shifts — all of which
satisfy the "strong evidence" definition in `PRODUCT_SPEC.md` §Evidence. A manual/CLI evidence
entry path is also implemented, conforming to the evidence contract, for evidence a human supplies
(e.g. a beat reporter's report copied in by a user). Fully automated ingestion of "medium"/"weak"
tier evidence (beat reports, social media, camp buzz) is BLOCKED for lack of a reachable source.

## D6 — League context source
`Sleeper` (the natural live source for roster/draft/waiver state per `PRODUCT_SPEC.md`) is
blocked. League context is loaded from a local YAML file matching the
`AGENT_CONTRACTS.md` league-context contract exactly. The Sleeper adapter is implemented and will
hydrate the same contract automatically once reachable — no schema change required.

## D7 — Target league type
`ARCHITECTURE.md`/`IMPLEMENTATION_PLAN.md`/`PRODUCT_SPEC.md` all state the target league is 10
teams, 2 QB, 2 RB, 2 WR, 1 TE, 2 FLEX. `AGENT_CONTRACTS.md`'s worked example additionally sets
`"format": "dynasty"`. Neither bench size nor FAAB budget is specified anywhere.
**Decision:** treat the target league as dynasty PPR (per the contract example), and produce both
redraft-season and dynasty outputs (both are required product outputs per
`ACCEPTANCE_CRITERIA.md`; nothing says the target league is the only league instance). Default
bench = 10, FAAB budget = $100 — both configurable per-league, documented here as defaults, not
silently assumed.

## D8 — Team-season Monte Carlo simulation
`PRODUCT_SPEC.md` §Simulation says "eventually" and `ARCHITECTURE.md` calls it
"later-stage." Scheduled as M13 (after the validated core), not dropped.

## D9 — No third-party data committed to git
`ARCHITECTURE.md` §15 prohibits distributing proprietary source data without rights. `data/`,
`models/`, `predictions/`, `reports/`, `state/` are gitignored. Test fixtures are schema-accurate
synthetic data (same columns/types as real sources, invented values), never a copy of a real
snapshot — this also keeps the test suite fast and network-independent.

## D10 — Agents are deterministic services, not LLM calls
`ARCHITECTURE.md` §6: "The project orchestrator is an engineering orchestration layer, not itself
the source of fantasy truth." Agents in `src/alpha_squad/agents/` are typed Python
functions/classes producing `AGENT_CONTRACTS.md`-shaped results, orchestrated by a DAG scheduler.
No agent calls an LLM to produce a projection, ranking, or recommendation — all fantasy-relevant
output comes from the deterministic model/market/league modules those agents wrap.
