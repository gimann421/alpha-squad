"""W16 --- render a saved beta weekly-board snapshot as one self-contained HTML page.

The page only DISPLAYS the snapshot: every ranking is the precomputed order in
`snapshot["boards"]` (built by `alpha_squad.beta.weekly_board.rank_view`), so there is exactly
one ranking implementation. Filters hide rows; they never re-rank.

    uv run python scripts/beta/render_board_html.py reports/beta/weekly_board_2026_w05_<id>.json \\
        --out reports/beta/weekly_board.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("board_template.html")


def compact(snap: dict) -> dict:
    players = snap["players"]
    idx = {p["player_id"]: i for i, p in enumerate(players)}
    rows = []
    for p in players:
        pr = p["projections"]
        rows.append(
            {
                "id": p["player_id"],
                "n": p["name"],
                "pos": p["position"],
                "tm": p["team"],
                "opp": p["opponent"],
                "home": p["home"],
                "ko": p["kickoff_utc"],
                "started": p["game_started"],
                "rs": p["roster_status"],
                "inj": p["injury_status"],
                "pc": pr["alpha_control"],
                "pw": pr["w10_experimental"],
                "sc": p["projection_source"]["alpha_control"],
                "sw": p["projection_source"]["w10_experimental"],
                "in": p["inputs"],
            }
        )
    boards = {
        m: {
            s: {v: [idx[i] for i in order] for v, order in views.items()}
            for s, views in by_s.items()
        }
        for m, by_s in snap["boards"].items()
    }
    meta = {
        k: snap[k]
        for k in (
            "snapshot_id",
            "beta_version",
            "season",
            "week",
            "generated_at",
            "cutoff",
            "disclaimer",
            "scoring",
            "models",
            "exclusions",
            "unprojected",
            "checks",
            "roster_week_used",
        )
    }
    meta["data_sources"] = [
        {k: d.get(k) for k in ("source", "dataset", "captured_at", "sha256")}
        for d in snap["data_sources"]
    ]
    return {"meta": meta, "players": rows, "boards": boards}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    snap = json.loads(Path(args.snapshot).read_text())
    data = json.dumps(compact(snap), separators=(",", ":"), default=str).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", data)
    Path(args.out).write_text(html)
    print(f"wrote {args.out} ({len(html) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
