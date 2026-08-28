"""Pick-level attribution: where, specifically, does Alpha's draft diverge from consensus,
and did each divergence help or hurt realized starter points (docs/DECISIONS.md D58)?

The aggregate benchmark (`evaluation/draft_simulation.py`) says *whether* Alpha beats
consensus. It cannot say *which picks* caused the gap, and the M17 forensic audit established
that aggregates actively hide the answer -- both pathological drafts it traced were decided
in the team's first one or two picks, which no season-level total reveals.

Method, and its one important subtlety. Alpha's draft and a consensus draft diverge as soon
as they make different picks, so replaying them side by side compares two different available
pools and attributes nothing. Instead this replays **Alpha's** draft once and, at each of
Alpha's turns, asks what the consensus *rule* would have taken **from the same pool at the
same moment**. That is a real counterfactual at a real decision point, with no divergence.

`starter_points_delta` then swaps that one pick into Alpha's final roster, holding all other
picks fixed, and recomputes the best legal lineup. Positive means the consensus alternative
would have produced more starter points, i.e. Alpha's pick cost the team.

**What this does not capture, stated rather than implied:** the swap is a single-pick
counterfactual. It does not model how taking a different player would have changed which
players were available at later picks. Those downstream effects are real; a full accounting
would need a re-simulation per pick, which is a different (and far more expensive) analysis.
Read a single row as "holding the rest of the draft fixed, this pick was worth X", not as
"this pick cost the season X".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.evaluation.draft_simulation import (
    _actual_points_for,
    _market_consensus_pick,
    _next_pick_overall,
    _snake_overall_pick,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import (
    picks_until_next_turn,
    positional_opportunity_cost,
)
from alpha_squad.league.replacement import (
    compute_league_starters,
    load_season_projections,
    marginal_value_over_replacement,
)
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import resolve_market_series
from alpha_squad.sources.base import utcnow


@dataclass
class PickAttribution:
    season: int
    draft_slot: int
    round_no: int
    overall_pick: int
    alpha_player_id: str
    alpha_position: str
    alpha_projected: float
    alpha_vorp: float
    alpha_realized: float
    consensus_player_id: str
    consensus_position: str
    consensus_projected: float
    consensus_vorp: float
    consensus_realized: float
    agreed: bool
    roster_before: dict[str, int]
    opportunity_cost_alpha_position: float
    opportunity_cost_consensus_position: float
    starter_points_delta: float


def _lineup_points(
    league: LeagueContext,
    roster: list[str],
    positions: dict[str, str],
    actual_points: dict[str, float],
) -> float:
    """Best legal starting lineup this roster could field, scored on real season totals.
    `teams: 1` scopes the slot allocation to a single team's roster rather than the league."""
    scoped = league.model_copy(update={"teams": 1})
    points = {p: actual_points.get(p, 0.0) for p in roster}
    starters = compute_league_starters(
        scoped, points, {p: positions.get(p, "UNKNOWN") for p in roster}
    )
    return sum(points.get(p, 0.0) for p in starters["starters"])


def attribute_draft_picks(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    draft_slot: int,
    *,
    ecr_type: str | None = None,
) -> list[PickAttribution]:
    """One row per pick the team in question makes, with its consensus counterfactual."""
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type

    projections, positions = load_season_projections(con, season)
    vorp = marginal_value_over_replacement(league, projections, positions)
    market_rank = _preseason_overall_market(con, ecr_type, season)
    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    available = set(projections)
    my_roster: list[str] = []
    my_roster_positions: list[str] = []
    records: list[tuple] = []

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        for slot in order:
            if not available:
                break
            if slot != draft_slot:
                available.discard(_market_consensus_pick(available, market_rank))
                continue

            overall = _snake_overall_pick(round_no, slot, league.teams)
            next_pick = _next_pick_overall(round_no, slot, league.teams, total_rounds)
            rec = recommend_draft_pick(
                con,
                league,
                season,
                my_roster_positions,
                available,
                next_pick_overall=next_pick,
                ecr_type=ecr_type,
                top_n=1,
                current_pick_overall=overall,
            )
            alpha_pick = rec.recommendation
            consensus_pick = _market_consensus_pick(available, market_rank)

            # Opportunity costs as of this exact decision point, for both positions in play.
            n_opponent_picks = picks_until_next_turn(overall, next_pick)
            wanted = [positions.get(alpha_pick, ""), positions.get(consensus_pick, "")]
            costs = (
                positional_opportunity_cost(
                    set(available), positions, vorp, market_rank, n_opponent_picks, wanted
                )
                if n_opponent_picks > 0
                else dict.fromkeys(wanted, 0.0)
            )

            roster_before: dict[str, int] = {}
            for pos in my_roster_positions:
                roster_before[pos] = roster_before.get(pos, 0) + 1

            records.append(
                (round_no, overall, alpha_pick, consensus_pick, dict(roster_before), costs)
            )
            my_roster.append(alpha_pick)
            my_roster_positions.append(positions.get(alpha_pick, "UNKNOWN"))
            available.discard(alpha_pick)

    # Realized outcomes are looked up once, for Alpha's roster and every counterfactual.
    all_ids = sorted({r[2] for r in records} | {r[3] for r in records})
    actual_points = _actual_points_for(con, season, all_ids)
    baseline_starter_points = _lineup_points(league, my_roster, positions, actual_points)

    out: list[PickAttribution] = []
    for round_no, overall, alpha_pick, consensus_pick, roster_before, costs in records:
        if alpha_pick == consensus_pick:
            delta = 0.0
        else:
            swapped = [consensus_pick if p == alpha_pick else p for p in my_roster]
            delta = (
                _lineup_points(league, swapped, positions, actual_points) - baseline_starter_points
            )
        alpha_pos = positions.get(alpha_pick, "UNKNOWN")
        cons_pos = positions.get(consensus_pick, "UNKNOWN")
        out.append(
            PickAttribution(
                season=season,
                draft_slot=draft_slot,
                round_no=round_no,
                overall_pick=overall,
                alpha_player_id=alpha_pick,
                alpha_position=alpha_pos,
                alpha_projected=projections.get(alpha_pick, 0.0),
                alpha_vorp=vorp.get(alpha_pick, 0.0),
                alpha_realized=actual_points.get(alpha_pick, 0.0),
                consensus_player_id=consensus_pick,
                consensus_position=cons_pos,
                consensus_projected=projections.get(consensus_pick, 0.0),
                consensus_vorp=vorp.get(consensus_pick, 0.0),
                consensus_realized=actual_points.get(consensus_pick, 0.0),
                agreed=alpha_pick == consensus_pick,
                roster_before=roster_before,
                opportunity_cost_alpha_position=costs.get(alpha_pos, 0.0),
                opportunity_cost_consensus_position=costs.get(cons_pos, 0.0),
                starter_points_delta=delta,
            )
        )
    return out


def run_pick_attribution(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    seasons: list[int],
    slots: list[int] | None = None,
    *,
    ecr_type: str | None = None,
) -> list[PickAttribution]:
    slots = slots if slots is not None else list(range(1, league.teams + 1))
    rows: list[PickAttribution] = []
    for season in seasons:
        for slot in slots:
            rows.extend(attribute_draft_picks(con, league, season, slot, ecr_type=ecr_type))
    return rows


def write_pick_attribution_artifacts(
    rows: list[PickAttribution], json_path: Path, report_path: Path
) -> None:
    """Raw rows as JSON (so the analysis is auditable and re-checkable without re-running the
    drafts) plus a Markdown summary."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "framework_version": EVALUATION_FRAMEWORK_VERSION,
                "generated_at": utcnow().isoformat(),
                "picks": [asdict(r) for r in rows],
            },
            indent=2,
            sort_keys=True,
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(rows))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _render_report(rows: list[PickAttribution]) -> str:
    if not rows:
        return "# Pick-level attribution\n\nNo picks recorded.\n"

    disagreements = [r for r in rows if not r.agreed]
    hurt = [r for r in disagreements if r.starter_points_delta > 0]
    helped = [r for r in disagreements if r.starter_points_delta < 0]

    lines = [
        "# Pick-level attribution: Alpha vs market consensus",
        "",
        "Generated by `evaluation/pick_attribution.py`. `starter_points_delta > 0` means the",
        "consensus alternative would have scored MORE starter points, i.e. Alpha's pick cost",
        "the team. Single-pick counterfactual: downstream availability effects are not",
        "modelled (see the module docstring).",
        "",
        "## Summary",
        "",
        f"- picks analysed: **{len(rows)}**",
        f"- Alpha agreed with consensus: **{len(rows) - len(disagreements)}** "
        f"({100 * (len(rows) - len(disagreements)) / len(rows):.1f}%)",
        f"- disagreements: **{len(disagreements)}**",
        f"- of those, cost starter points: **{len(hurt)}**; gained: **{len(helped)}**",
        f"- mean delta across disagreements: **{_mean([r.starter_points_delta for r in disagreements]):+.1f}**",
        f"- total delta across disagreements: **{sum(r.starter_points_delta for r in disagreements):+.1f}**",
        "",
        "## By round",
        "",
        "| Round | picks | disagreements | mean delta | total delta |",
        "|---|---|---|---|---|",
    ]
    rounds = sorted({r.round_no for r in rows})
    for round_no in rounds:
        in_round = [r for r in rows if r.round_no == round_no]
        disagreed = [r for r in in_round if not r.agreed]
        deltas = [r.starter_points_delta for r in disagreed]
        lines.append(
            f"| {round_no} | {len(in_round)} | {len(disagreed)} | "
            f"{_mean(deltas):+.1f} | {sum(deltas):+.1f} |"
        )

    lines += [
        "",
        "## By position Alpha took (when it disagreed)",
        "",
        "| Alpha took | consensus took | n | mean delta | total delta |",
        "|---|---|---|---|---|",
    ]
    pairs = sorted({(r.alpha_position, r.consensus_position) for r in disagreements})
    pair_rows = []
    for alpha_pos, cons_pos in pairs:
        matching = [
            r
            for r in disagreements
            if r.alpha_position == alpha_pos and r.consensus_position == cons_pos
        ]
        deltas = [r.starter_points_delta for r in matching]
        pair_rows.append((sum(deltas), alpha_pos, cons_pos, len(matching), _mean(deltas)))
    for total, alpha_pos, cons_pos, n, mean in sorted(pair_rows, reverse=True):
        lines.append(f"| {alpha_pos} | {cons_pos} | {n} | {mean:+.1f} | {total:+.1f} |")

    lines += [
        "",
        "## Worst individual picks",
        "",
        "| Season | Slot | Rd | Alpha took | proj | real | Consensus | proj | real | delta |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(disagreements, key=lambda r: -r.starter_points_delta)[:20]:
        lines.append(
            f"| {r.season} | {r.draft_slot} | {r.round_no} | "
            f"{r.alpha_position} {r.alpha_player_id} | {r.alpha_projected:.0f} | "
            f"{r.alpha_realized:.0f} | {r.consensus_position} {r.consensus_player_id} | "
            f"{r.consensus_projected:.0f} | {r.consensus_realized:.0f} | "
            f"{r.starter_points_delta:+.1f} |"
        )
    return "\n".join(lines) + "\n"
