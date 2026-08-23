"""PRODUCT_SPEC.md's Strong/Medium/Weak evidence hierarchy, verbatim. Every `event_type`
this project can actually produce is mapped here to its exact PRODUCT_SPEC label; the
Medium/Weak examples are also registered (with no detector behind them, per
docs/DECISIONS.md D5/D22) so the hierarchy itself is a complete, structural implementation
of PRODUCT_SPEC's taxonomy, not just the subset this environment's reachable sources
happen to cover."""

from __future__ import annotations

STRONG = "STRONG"
MEDIUM = "MEDIUM"
WEAK = "WEAK"

# Numeric strength per AGENT_CONTRACTS.md's Evidence contract field (a 0-1 float, e.g. 0.95).
STRENGTH_SCORE = {STRONG: 0.9, MEDIUM: 0.5, WEAK: 0.2}

# event_type -> PRODUCT_SPEC.md label. Only the STRONG entries below have a real detector
# (evidence/events.py) in this environment -- Medium/Weak sources (beat reporters, coach
# comments, social media, practice-participation text feeds) require a news/social API this
# environment cannot reach (D5). They are registered here as the manual-entry path's
# vocabulary: a human or a future integration can still insert a structured event of these
# types through record_event(), conforming to the same contract, without a code change.
EVENT_TYPE_STRENGTH: dict[str, str] = {
    # Strong -- real detectors, all built on officially-sourced nflverse structured data.
    "depth_chart_promotion": STRONG,
    "depth_chart_demotion": STRONG,
    "injury_own_status": STRONG,
    "injury_teammate_opportunity": STRONG,
    "roster_transaction": STRONG,
    "usage_share_spike": STRONG,
    "usage_share_drop": STRONG,
    # Medium -- vocabulary only, no reachable source (D5); manual-entry path.
    "beat_writer_report": MEDIUM,
    "coach_comment": MEDIUM,
    "strong_practice_report": MEDIUM,
    # Weak -- vocabulary only, no reachable source (D5); manual-entry path.
    "highlight_clip": WEAK,
    "generic_praise": WEAK,
    "social_media_buzz": WEAK,
    "speculative_commentary": WEAK,
}


def strength_for(event_type: str) -> tuple[str, float]:
    """(label, numeric score) for a registered event_type. Unknown types are refused rather
    than silently defaulting -- an evidence event with no defensible strength is worse than
    no event at all."""
    if event_type not in EVENT_TYPE_STRENGTH:
        raise ValueError(f"unregistered evidence event_type: {event_type!r}")
    label = EVENT_TYPE_STRENGTH[event_type]
    return label, STRENGTH_SCORE[label]
