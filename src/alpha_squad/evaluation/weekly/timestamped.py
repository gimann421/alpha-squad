"""Timestamped pre-Friday information and RB breakouts (W12). Pure functions, no I/O.

W11 found W10's historical model loses capture on sustained RB risers because it cannot tell the
rare real breakout from the common blip, and that current-role features do not help. W12
(`docs/weekly/W12_PREREGISTRATION.md`) asks whether **verified pre-Friday** information -- the NFL
injury report, the only Class A source for the week's changing roles (`docs/weekly/W12_DATA_AUDIT.md`)
-- can. This module holds the cutoff rule, the injury-report feature definitions and the
pre-registered verdict order.
"""

from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

#: 2015-2019 injury rows keep relocated teams' old codes; stats and games use the new ones.
TEAM_ALIAS: dict[str, str] = {"OAK": "LV", "SD": "LAC", "STL": "LA"}

OUTISH = frozenset({"Out", "Doubtful"})
QUESTIONABLE = "Questionable"
STATUS_CODE = {"Questionable": 1.0, "Doubtful": 2.0, "Out": 3.0}
PRACTICE_CODE = {
    "Full Participation in Practice": 0.0,
    "Limited Participation in Practice": 1.0,
    "Did Not Participate In Practice": 2.0,
    "Out (Definitely Will Not Play)": 2.0,
}
FEATURES: tuple[str, ...] = ("tm_out_opp", "tm_q_opp", "tm_ret_opp", "own_status", "own_practice")
CATEGORIES: dict[str, tuple[str, ...]] = {
    "teammate": ("tm_out_opp", "tm_q_opp", "tm_ret_opp"),
    "own": ("own_status", "own_practice"),
}
WINDOW = 3
VACANCY_TOUCHES = 8.0

#: Verdict thresholds (§7).
SUCCESS_BAR = 0.02
BREACH_FLOOR = 0.005
WR_MATERIAL = 0.01
MIN_SEASONS_POSITIVE = 3
MIN_LOSO_SIGNIFICANT = 3
MIN_RISERS = 300
MIN_VACANCY = 30
MIN_BREAKOUTS = 40
MIN_VACANCY_WEEKS = 20


# ---------------------------------------------------------------------------------------
# The cutoff
# ---------------------------------------------------------------------------------------


def friday_before(first_sunday: dt.date) -> dt.date:
    """The Friday before a week's first Sunday game."""
    return first_sunday - dt.timedelta(days=(first_sunday.weekday() - 4) % 7 or 7)


def cutoff_instant(friday: dt.date, strict: bool = False) -> dt.datetime:
    """23:59:59 ET on the cutoff Friday (primary), or 00:00:00 ET that day (strict)."""
    t = dt.time(0, 0, 0) if strict else dt.time(23, 59, 59)
    return dt.datetime.combine(friday, t, tzinfo=ET)


def team_code(code: str | None) -> str | None:
    return TEAM_ALIAS.get(code, code) if code else code


# ---------------------------------------------------------------------------------------
# The injury-report features
# ---------------------------------------------------------------------------------------


def touches_per_game(games: list[tuple[int, float]], week: int) -> float:
    """Mean touches over the last WINDOW appearances before `week` (0 with none)."""
    prior = [t for w, t in sorted(games) if w < week][-WINDOW:]
    return math.fsum(prior) / len(prior) if prior else 0.0


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def features(
    player_id: str,
    position: str,
    rows: list[dict],
    cutoff: dt.datetime,
    tpg: dict[str, float],
    missed_last: set[str],
) -> dict[str, float | None]:
    """The five §4 features for one player-week from its team's week-w report.

    `rows`: every report row of the player's team for the week, each with `player_id`,
    `position`, `status`, `practice` and `modified` (an aware datetime). Rows modified after
    `cutoff` are treated as if they did not exist, so deleting them can never change a feature
    (gate G2). If no row is at or before `cutoff`, the report is not observable and every
    feature is missing. `tpg`: teammates' touches per game. `missed_last`:
    players who appeared this season but not in the team's most recent game."""
    known = [r for r in rows if r["modified"] <= cutoff]
    if not known:
        return {f: None for f in FEATURES}
    assert all(r["modified"] <= cutoff for r in known)
    parts: dict[str, list[float]] = {"tm_out_opp": [], "tm_q_opp": [], "tm_ret_opp": []}
    for r in known:
        pid = r["player_id"]
        if pid is None or pid == player_id or r["position"] != position:
            continue
        load = tpg.get(pid, 0.0)
        if r["status"] in OUTISH:
            parts["tm_out_opp"].append(load)
            continue
        if r["status"] == QUESTIONABLE:
            parts["tm_q_opp"].append(load)
        if pid in missed_last:
            parts["tm_ret_opp"].append(load)
    out: dict[str, float | None] = {k: math.fsum(v) for k, v in parts.items()}
    # Only rows at or before the cutoff exist for this computation (amendment A1): a player whose
    # only row was edited later counts as not listed. Marking such a player "unknown" instead
    # would reveal that a post-cutoff edit happened -- post-Friday information.
    own = [r for r in known if r["player_id"] == player_id]
    out["own_status"] = max((STATUS_CODE.get(r["status"], 0.0) for r in own), default=0.0)
    out["own_practice"] = max((PRACTICE_CODE.get(r["practice"], 0.0) for r in own), default=0.0)
    return out


def vacancy(feats: dict) -> bool | None:
    v = feats.get("tm_out_opp")
    return None if _missing(v) else float(v) >= VACANCY_TOUCHES


# ---------------------------------------------------------------------------------------
# The pre-registered verdict (§7)
# ---------------------------------------------------------------------------------------


def coverage_ok(c: dict) -> bool:
    return (
        c.get("risers", 0) >= MIN_RISERS
        and c.get("vacancy", 0) >= MIN_VACANCY
        and c.get("breakouts", 0) >= MIN_BREAKOUTS
        and c.get("vacancy_weeks", 0) >= MIN_VACANCY_WEEKS
    )


def _pos(r: dict | None) -> bool:
    return bool(r) and r["ci_low"] > 0.0


def is_breach(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0 and abs(r["mean_diff"]) >= BREACH_FLOOR


def verdict(inputs: dict) -> dict:
    """`inputs`: coverage (counts), qa1 (ratio-difference row), rb (D − C RB capture@10),
    rb_null (D − N), rb_seasons (point estimates), rb_loso (rows), guard ({name: D − C row}),
    wr (D − C WR capture@10), wr_vs_a (D − A WR capture@10)."""
    if not coverage_ok(inputs.get("coverage", {})):
        return {"verdict": "DATA INSUFFICIENT", "conditions": {}, "breaches": []}
    rb = inputs.get("rb")
    breaches = sorted(n for n, r in inputs.get("guard", {}).items() if is_breach(r))
    wr = inputs.get("wr")
    wr_harm = not (bool(wr) and not is_breach(wr) and wr["mean_diff"] > -WR_MATERIAL)
    c = {
        "B1_rb_bar": _pos(rb) and rb["mean_diff"] >= SUCCESS_BAR,
        "B2_beats_null": _pos(inputs.get("rb_null")),
        "B3_consistent": (
            sum(1 for v in inputs.get("rb_seasons", []) if v > 0) >= MIN_SEASONS_POSITIVE
            and sum(1 for r in inputs.get("rb_loso", []) if _pos(r)) >= MIN_LOSO_SIGNIFICANT
        ),
        "B4_no_breach": not breaches,
        "B5_wr_kept": not wr_harm and _pos(inputs.get("wr_vs_a")),
    }
    qa1 = inputs.get("qa1")
    info = bool(qa1) and qa1["ci_low"] > 0.0
    if all(c.values()):
        label = "INFORMATION EXISTS + ACTIONABLE"
    elif c["B1_rb_bar"] and (breaches or wr_harm):
        label = "TRADEOFF"
    elif breaches or wr_harm:
        label = "HARM"
    elif info:
        label = "INFORMATION EXISTS + NOT ACTIONABLE"
    else:
        label = "NO INCREMENTAL SIGNAL"
    return {
        "verdict": label,
        "conditions": c,
        "information_exists": info,
        "breaches": breaches,
        "wr_harm": wr_harm,
    }
