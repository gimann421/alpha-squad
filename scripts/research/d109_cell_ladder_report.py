"""Aggregate the Part 4 cell-ladder results."""

import json
import os
from collections import Counter
from statistics import median


def _load(path: str):
    with open(path) as f:
        return json.load(f)


def _dump(obj, path: str) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, default=str)


#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SP = SP
LADDER = [0, 10, 20, 30, 40, 55, 70, 90, 120, 160]

rows = []
for s in (2021, 2022, 2023, 2024, 2025):
    rows.extend(_load(f"{SP}/p4b_{s}.json"))

# The measured RB under-projection inside the contention set (Part 1, median-based,
# conditional on market rank): -55.8 / -45.7 / -24.9 at ECR 1-12 / 13-24 / 25-36.
MEASURED = 41.5  # mean bias inside ECR<=30, pooled
MEASURED_MAX = 55.8  # the largest band-level bias measured

non_rb = [r for r in rows if r["pick_position"] != "RB"]
print(f"Cell-ladder counterfactual: {len(rows)} pick states, {len(non_rb)} where Alpha did NOT take an RB")
print("Question: how much would EVERY RB with preseason ECR<=36 have to gain before the")
print("production engine takes an RB at that pick?\n")

print(f"{'round':<7}{'n':>4}{'flips<=40':>11}{'flips<=56':>11}{'flips<=90':>11}{'never<=160':>12}{'median d':>10}")
for rnd in (1, 2, 3):
    sub = [r for r in non_rb if r["round"] == rnd]
    if not sub:
        continue
    f = [r["flip_to_rb_at"] for r in sub]
    never = sum(1 for x in f if x is None)
    got = [x for x in f if x is not None]
    print(
        f"{rnd:<7}{len(sub):>4}"
        f"{sum(1 for x in got if x <= 40):>11}"
        f"{sum(1 for x in got if x <= 55):>11}"
        f"{sum(1 for x in got if x <= 90):>11}"
        f"{never:>12}"
        f"{(median(got) if got else float('nan')):>10.0f}"
    )
sub = non_rb
f = [r["flip_to_rb_at"] for r in sub]
got = [x for x in f if x is not None]
never = sum(1 for x in f if x is None)
print(
    f"{'ALL':<7}{len(sub):>4}"
    f"{sum(1 for x in got if x <= 40):>11}"
    f"{sum(1 for x in got if x <= 55):>11}"
    f"{sum(1 for x in got if x <= 90):>11}"
    f"{never:>12}"
    f"{(median(got) if got else float('nan')):>10.0f}"
)

print(f"\n  within the MEASURED bias ({MEASURED:.1f} pts, mean inside ECR<=30): "
      f"{sum(1 for x in got if x <= MEASURED)}/{len(sub)} = {sum(1 for x in got if x <= MEASURED) / len(sub):.0%}")
print(f"  within the LARGEST band bias ({MEASURED_MAX:.1f} pts, ECR 1-12): "
      f"{sum(1 for x in got if x <= MEASURED_MAX)}/{len(sub)} = {sum(1 for x in got if x <= MEASURED_MAX) / len(sub):.0%}")
print(f"  still not an RB at +160: {never}/{len(sub)} = {never / len(sub):.0%}")

print("\nBY SEASON (does it track the market regime?)")
print(f"{'season':<8}{'n':>4}{'flips<=56':>11}{'never<=160':>12}{'median d':>10}")
for s in (2021, 2022, 2023, 2024, 2025):
    sub = [r for r in non_rb if r["season"] == s]
    if not sub:
        continue
    f = [r["flip_to_rb_at"] for r in sub]
    got = [x for x in f if x is not None]
    print(
        f"{s:<8}{len(sub):>4}{sum(1 for x in got if x <= 55):>11}"
        f"{sum(1 for x in f if x is None):>12}{(median(got) if got else float('nan')):>10.0f}"
    )

print("\nBY THE POSITION ALPHA ACTUALLY TOOK")
print(f"{'pos':<6}{'n':>4}{'flips<=56':>11}{'never<=160':>12}{'median d':>10}")
for pos in ("WR", "QB", "TE"):
    sub = [r for r in non_rb if r["pick_position"] == pos]
    if not sub:
        continue
    f = [r["flip_to_rb_at"] for r in sub]
    got = [x for x in f if x is not None]
    print(
        f"{pos:<6}{len(sub):>4}{sum(1 for x in got if x <= 55):>11}"
        f"{sum(1 for x in f if x is None):>12}{(median(got) if got else float('nan')):>10.0f}"
    )

print("\nWHAT THE LADDER CONVERGES TO (position mix at each delta, all 150 states)")
print(f"{'delta':<8}" + "".join(f"{p:>7}" for p in ("QB", "RB", "WR", "TE")))
for d in LADDER:
    c = Counter(r["ladder"][str(d)] if str(d) in r["ladder"] else r["ladder"].get(d) for r in rows)
    print(f"{d:<8}" + "".join(f"{c.get(p, 0):>7}" for p in ("QB", "RB", "WR", "TE")))
