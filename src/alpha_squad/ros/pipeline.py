"""Glue: raw files -> panel parquet (+ provenance manifest)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.ros import snapshots as sn
from alpha_squad.ros.ingest import ensure_inputs, write_manifest
from alpha_squad.ros.scoring import ScoringRules

DEFAULT_OUT = Path("data/ros")
#: Snapshot weeks built for model TRAINING (earlier seasons only ever feed training); the
#: pre-specified EVALUATION weeks are `snapshots.DEFAULT_WEEKS` (6-10).
TRAIN_WEEKS = tuple(range(3, 14))


def load_inputs(
    seasons: list[int],
    rules: ScoringRules,
    settings: Settings | None = None,
    *,
    refresh: bool = False,
) -> tuple[sn.RosInputs, dict]:
    settings = settings or get_settings()
    need = sorted({s for s in seasons} | {min(seasons) - 1})
    files = ensure_inputs(need, settings, refresh=refresh)
    paths = lambda ds: {s: f.path for s, f in files[ds].items()}  # noqa: E731
    ecr = sn.load_ecr_qb(files["ecr"].path)
    pbp_seasons = {s: p for s, p in paths("pbp").items() if s in seasons}
    pbp_player, pbp_team = sn.load_pbp_tables(pbp_seasons)
    prov = {
        "ecr_archive": sn.describe_ecr_archive(ecr),
        "files": {
            k: ({str(s): vars(f) for s, f in v.items()} if isinstance(v, dict) else vars(v))
            for k, v in files.items()
        },
    }
    inp = sn.prepare_inputs(
        ecr=ecr,
        id_map=sn.load_id_map(files["player_ids"].path),
        schedule=sn.load_schedule(files["schedule"].path),
        stats=sn.load_weekly_stats(paths("stats_player_week")),
        pbp_player=pbp_player,
        pbp_team=pbp_team,
        injuries=sn.load_injuries({s: p for s, p in paths("injuries").items() if s in seasons}),
        rules=rules,
        provenance=prov,
    )
    return inp, files


def build_default_panel(
    seasons: list[int],
    rules: ScoringRules | None = None,
    weeks=TRAIN_WEEKS,
    out_dir: Path = DEFAULT_OUT,
    settings: Settings | None = None,
    horizon_week: int = sn.DEFAULT_HORIZON_WEEK,
) -> tuple[pd.DataFrame, sn.RosInputs]:
    rules = rules or ScoringRules.nflverse_ppr()
    inp, files = load_inputs(seasons, rules, settings)
    inp.provenance["_files"] = files
    specs = sn.select_snapshots(
        sorted(set(inp.ecr["scrape_date"])), inp.schedule, seasons, weeks=weeks
    )
    panel = sn.build_panel(inp, specs, horizon_week=horizon_week)
    panel["eval_week"] = panel["snapshot_week"].isin(sn.DEFAULT_WEEKS)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out_dir / "qb_ros_panel.parquet", index=False)
    write_manifest(files, out_dir / "inputs_manifest.json")
    skipped = [
        (s, w)
        for s in seasons
        for w in weeks
        if not any(sp.season == s and sp.week == w for sp in specs)
    ]
    meta = {
        "scoring": rules.describe(),
        "snapshots": [
            {"season": sp.season, "week": sp.week, "scrape_date": str(sp.scrape_date)}
            for sp in specs
        ],
        "skipped_season_weeks": skipped,
        "n_rows": int(len(panel)),
    }
    (out_dir / "panel_meta.json").write_text(json.dumps(meta, indent=2))
    inp.provenance["_specs"] = specs
    return panel, inp


def build_skill_panel(
    inp: sn.RosInputs,
    specs: list[sn.SnapshotSpec],
    files: dict,
    out_dir: Path = DEFAULT_OUT,
    horizon_week: int = sn.DEFAULT_HORIZON_WEEK,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All-position (QB/RB/WR/TE) board + realized weekly points for roster-level evaluation."""
    from alpha_squad.ros import skill

    overall = skill.load_ecr_overall(files["ecr"].path)
    ps, ws = [], []
    for sp in specs:
        p, w = skill.build_skill_snapshot(inp, overall, sp, horizon_week=horizon_week)
        ps.append(p)
        ws.append(w)
    players = pd.concat([x for x in ps if len(x)], ignore_index=True)
    weekly = pd.concat([x for x in ws if len(x)], ignore_index=True)
    complete = {(sp.season, sp.week) for sp in specs}
    del complete
    out_dir.mkdir(parents=True, exist_ok=True)
    players.to_parquet(out_dir / "skill_players.parquet", index=False)
    weekly.to_parquet(out_dir / "skill_weekly.parquet", index=False)
    return players, weekly
