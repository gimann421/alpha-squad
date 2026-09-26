"""W10 post-hoc check (amendment A2): arm B against the permuted-feature null N, directly.

**Post-hoc, written after the W10 results were read, and never a verdict input.** The null arm
N (B's seven columns permuted across players within season) reached +0.014 at WR capture@5 over
the full season and +0.043 (CI excluding 0) in the EARLY period. So "B beats A" at capture@5
might partly be "any perturbation of the model beats A". This asks the sharper question: does B
beat N? It reads only the committed per-week cells in `reports/weekly/w10_results.json`.

    uv run python scripts/research/w10_posthoc.py --out reports/weekly/w10_posthoc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import diagnostics, mechanisms, noise  # noqa: E402

ARM_B = "ALPHA_PLUS_HISTORICAL"
ARM_N = "ALPHA_PLUS_HISTORICAL_NULL"
POSITIONS = ("RB", "WR", "TE", "FLEX")
METRICS = ("capture@5", "capture@10", "capture@20", "spearman")


def _series(cells: dict, system: str, metric: str, keep) -> dict[str, float]:
    return {
        k: r[metric]
        for k, r in cells.get(system, {}).items()
        if keep(k) and r.get(metric) is not None and not r.get("invalid")
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="reports/weekly/w10_results.json")
    ap.add_argument("--out", default="reports/weekly/w10_posthoc.json")
    args = ap.parse_args()
    res = json.loads(Path(args.results).read_text())
    week_of = {}
    for weeks in res["full_ppr"]["cells"].values():
        for k in weeks:
            week_of[k] = int(k.split("-")[1])
    windows = {"FULL": lambda k: True} | {
        name: (lambda k, n=name: mechanisms.period_of(week_of[k]) == n)
        for name, _lo, _hi in mechanisms.PERIODS
    }
    out: dict = {}
    for tag in ("full_ppr", "half_ppr"):
        cells = res[tag]["cells"]
        for window, keep in windows.items():
            for pos in POSITIONS:
                for m in METRICS:
                    a = _series(cells, f"{pos}|{ARM_B}", m, keep)
                    b = _series(cells, f"{pos}|{ARM_N}", m, keep)
                    pd_ = noise.paired_difference(m, ARM_B, ARM_N, a, b)
                    po = diagnostics.paired_outcome(m, ARM_B, ARM_N, a, b)
                    if pd_:
                        row = pd_.as_row()
                        if po:
                            o = po.as_row()
                            row.update(b_wins=o["a_wins"], n_wins=o["b_wins"], ties=o["ties"])
                        out.setdefault(tag, {}).setdefault(window, {}).setdefault(pos, {})[m] = row
    out["note"] = "POST-HOC (amendment A2). Not a verdict input."
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
