"""D91 — is Y1's marginal-starter-value DEGENERATE among bench candidates? (diagnostic)

Read-only. Touches nothing in `models/` or `league/`; it calls the shipped
`marginal_starter_value` and D86's `expected_weekly_marginal_value` and prints what each says
about the same candidate on the same roster.

Why this exists
---------------
D84 recorded that the incumbent objective "gives the bench a value of exactly zero", and D86
built a weekly objective to fix it. Five phases then described O1's behaviour through its most
visible consequence -- it drafts fewer kickers -- and D91 Track A showed that consequence is a
marker rather than the carrier of the gain (the kicker channel is OFF in target 2020 and the
season still returns +41.3; the season with the MOST kicker restraint, 2022, is the only season
O1 loses).

So this asks the question one level down: on a roster whose starting lineup is already full,
what does each objective say a BACKUP is worth?

    usage:  uv run python scripts/d91_msv_degeneracy.py [--season 2024] [--league target_league]
"""

from __future__ import annotations

import argparse

import duckdb

from alpha_squad.evaluation.draft_forensics import load_season_static, preseason_page_type
from alpha_squad.evaluation.weekly_objective import expected_weekly_marginal_value
from alpha_squad.league.context import resolve_league
from alpha_squad.league.replacement import marginal_starter_value
from alpha_squad.league.roster import startable_slots
from alpha_squad.market.series import resolve_market_series

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
#: Which player at each position stands in for "a backup" -- deep enough to be worse than every
#: incumbent on the saturated roster below, shallow enough to still be a real draftable body.
BACKUP_RANK = 20


def main(league_id: str, season: int, db: str) -> None:
    con = duckdb.connect(db, read_only=True)
    league = resolve_league(league_id, con=con)
    page = preseason_page_type(con, resolve_market_series(league).ecr_type, season)
    static = load_season_static(con, league, season, page_type=page)
    rates = static.availability_rates
    slots = startable_slots(league)

    by_pos: dict[str, list[tuple[float, str]]] = {}
    for pid, pos in static.positions.items():
        if pid in static.projections:
            by_pos.setdefault(pos, []).append((static.projections[pid], pid))
    for v in by_pos.values():
        v.sort(reverse=True)

    # Every starting slot filled with the best player available at it.
    roster = [
        by_pos["QB"][0][1],
        by_pos["RB"][0][1],
        by_pos["RB"][1][1],
        by_pos["WR"][0][1],
        by_pos["WR"][1][1],
        by_pos["TE"][0][1],
        by_pos["RB"][2][1],
        by_pos["WR"][2][1],  # the two FLEX slots
        by_pos["K"][0][1],
        by_pos["DST"][0][1],
    ]
    print(f"league={league_id} season={season} page={page}")
    print(
        f"measured availability (walk-forward on {season - 5}-{season - 1}): "
        + "  ".join(f"{k} {v:.3f}" for k, v in sorted(rates.items()))
    )
    print(
        f"\nroster: all 10 starting slots filled with elite players "
        f"{[static.positions[p] for p in roster]}"
    )
    print(
        f"candidate: the #{BACKUP_RANK} player at each position -- worse than every incumbent "
        "he could displace.\nThis is the choice the engine actually faces in rounds 11-16.\n"
    )

    hdr = f"  {'pos':<6}{'startable':>10}{'rate':>7}{'P(hole)':>9}{'proj':>8}{'Y1 msv':>9}{'O1 msv':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    y1_vals, o1_vals = {}, {}
    for pos in POSITIONS:
        cand = by_pos[pos][min(BACKUP_RANK - 1, len(by_pos[pos]) - 1)][1]
        y1 = marginal_starter_value(league, roster, cand, static.projections, static.positions)
        o1 = expected_weekly_marginal_value(
            league, roster, cand, static.projections, static.positions, rates
        )
        y1_vals[pos], o1_vals[pos] = y1, o1
        n, r = slots.get(pos, 0), rates.get(pos, 1.0)
        print(
            f"  {pos:<6}{n:>10}{r:>7.3f}{1 - r**n:>9.3f}"
            f"{static.projections[cand]:>8.1f}{y1:>9.2f}{o1:>9.2f}"
        )

    print(
        f"\n  Y1 spread across the six backups: {min(y1_vals.values()):.2f} .. "
        f"{max(y1_vals.values()):.2f}"
    )
    print(
        f"  O1 spread across the six backups: {min(o1_vals.values()):.2f} .. "
        f"{max(o1_vals.values()):.2f}"
    )
    print(
        f"\n  O1 separation RB-backup : K-backup = {o1_vals['RB'] / max(o1_vals['K'], 1e-9):.1f}x"
    )
    print(f"  availability ratio K : RB          = {rates['K'] / rates['RB']:.2f}x")
    print(f"  startable-slot ratio RB : K        = {slots['RB'] / max(slots['K'], 1):.0f}x")
    print(
        "\n  The separation tracks the SLOT COUNT, not the availability spread: P(a hole opens)\n"
        "  is 1 - rate**slots, and the exponent moves it far more than the base does.\n"
        "  Y1 cannot express any of it -- every backup prices at ~0, so the whole back half of\n"
        "  the draft falls through to daVORP and the multipliers, which D85 measured as\n"
        "  over-valuing K by 5.34x and DST by 8.10x."
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="target_league")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    a = ap.parse_args()
    main(a.league, a.season, a.db)
