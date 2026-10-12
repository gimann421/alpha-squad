"""W16 --- one command that refreshes the EXPERIMENTAL weekly beta board.

    uv run python scripts/beta/refresh.py --season 2026 --week 6

Steps, each refusing rather than warning:

1. **Verify the base.** `--base-db` must hash to `--expected-base-sha` (the verified W10 base,
   D125). Any other file is a different base, and the board would not be W10's model.
2. **Fresh copy.** Copy the base into a new work directory under `data/beta/` and verify the
   copy's hash. The base itself is never opened for writing.
3. **Schedule snapshot.** Download nflverse's schedule into the work directory and record its
   url, capture time and sha256. Alternatively, pass `--schedule <file>`.
4. **Production's own ingest into the copy**, with `ALPHA_SQUAD_DB_PATH` / `ALPHA_SQUAD_DATA_DIR`
   pointing at the work directory: `sources ingest`, `identity build`, `features build`.
5. **A2 row-order restore** against the base (`scripts/research/w14_row_order.py`). Production's
   loader must return the base's 2015-2025 sequence row for row, or this step fails.
6. **`train established`** (A1's weekly command), then `scripts/beta/weekly_board.py`. Its
   snapshot goes to `--out` (default `reports/beta`). Optionally render the HTML viewer.
7. **Re-verify the base hash**, and write `refresh_manifest.json` in the work directory.

**Separation from the frozen holdout.**

- Work directories must be under `data/beta/`.
- Outputs must not be under `reports/weekly/`.
- The holdout's own paths (`data/w14`, `data/w15`, any `data/wNN`, the base file itself) are
  refused.
- Nothing on the research path imports this file (`tests/beta/test_isolation.py`).
- A beta board is never a holdout observation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The verified W10 base (D125): the file W10, W14 and W15 reproduce byte-for-byte on.
VERIFIED_BASE_SHA256 = "fa8e32dbbb8942d890d38f0fad5c88981dc7f171238826abf13eb09ddd2a73c7"
SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
BETA_ROOT = Path("data/beta")
HOLDOUT_DATA = re.compile(r"^data/w\d+(/|$)")
HOLDOUT_REPORTS = Path("reports/weekly")


class RefreshError(RuntimeError):
    """A refresh precondition failed; nothing downstream ran."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_sha(path: Path, expected: str, what: str) -> str:
    if not path.is_file():
        raise RefreshError(f"{what} not found: {path}")
    got = sha256_file(path)
    if got != expected:
        raise RefreshError(f"{what} {path} has sha256 {got}, expected {expected}")
    return got


def _rel(path: Path) -> str:
    p = path if path.is_absolute() else (ROOT / path)
    p = p.resolve()
    try:
        return p.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def check_separation(workdir: Path, out: Path, base_db: Path) -> None:
    """Refuse any path that could touch the frozen holdout or the base."""
    w, o, b = _rel(workdir), _rel(out), _rel(base_db)
    beta = _rel(BETA_ROOT)
    if not w.startswith(beta + "/"):
        raise RefreshError(f"work directory must be a subdirectory of {beta}/, got {w}")
    if HOLDOUT_DATA.match(w) or HOLDOUT_DATA.match(o):
        raise RefreshError(f"{w if HOLDOUT_DATA.match(w) else o} is a holdout data path")
    rep = _rel(HOLDOUT_REPORTS)
    if o == rep or o.startswith(rep + "/"):
        raise RefreshError(f"beta output may not go under {rep}/ (holdout artifacts)")
    if w == b or b.startswith(w + "/"):
        raise RefreshError("the base database may not live inside the beta work directory")


def fresh_copy(base_db: Path, dest: Path, expected: str) -> str:
    """Copy the base to `dest` (which must not exist) and verify the copy's hash."""
    if dest.exists():
        raise RefreshError(f"{dest} already exists; a refresh always starts from a fresh copy")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_db, dest)
    return verify_sha(dest, expected, "fresh copy")


def capture_schedule(
    dest_dir: Path, url: str = SCHEDULE_URL, now: dt.datetime | None = None
) -> Path:
    now = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"games_{stamp}.parquet"
    with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:  # noqa: S310
        shutil.copyfileobj(r, f)
    manifest = {
        "url": url,
        "captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": _rel(path),
        "sha256": sha256_file(path),
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return path


@dataclass
class Plan:
    season: int
    week: int
    base_db: Path
    workdir: Path
    out: Path
    schedule: Path | None
    html: bool
    expected_sha: str
    steps: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def db(self) -> Path:
        return self.workdir / "alpha_squad_beta.duckdb"

    @property
    def env(self) -> dict[str, str]:
        return {
            "ALPHA_SQUAD_DB_PATH": _rel(self.db),
            "ALPHA_SQUAD_DATA_DIR": _rel(self.workdir),
        }


def build_plan(p: Plan, schedule: Path) -> list[tuple[str, list[str]]]:
    """The pipeline, in its required order. A2 runs after `features build` (which rewrites row
    order) and before `train established` (which reads it)."""
    s, db, logs = str(p.season), _rel(p.db), _rel(p.workdir / "logs")
    cli = ["uv", "run", "alpha-squad"]
    py = ["uv", "run", "python"]
    steps = [
        ("ingest", [*cli, "sources", "ingest", "--season-start", s, "--season-end", s]),
        ("identity", [*cli, "identity", "build"]),
        ("features", [*cli, "features", "build", "--season-start", s, "--season-end", s]),
        (
            "row_order_A2",
            [*py, "scripts/research/w14_row_order.py", "--db", db, "--canonical", _rel(p.base_db)],
        ),
        (
            "train",
            [
                *cli,
                "train",
                "established",
                "--season-start",
                s,
                "--season-end",
                s,
                "--report-path",
                f"{logs}/train_established.md",
            ],
        ),
        (
            "board",
            [
                *py,
                "scripts/beta/weekly_board.py",
                "--season",
                s,
                "--week",
                str(p.week),
                "--base-db",
                _rel(p.base_db),
                "--db",
                db,
                "--schedule",
                _rel(schedule),
                "--out",
                _rel(p.out),
            ],
        ),
    ]
    return steps


def run(p: Plan, dry_run: bool = False) -> dict:
    check_separation(p.workdir, p.out, p.base_db)
    base_sha = verify_sha(p.base_db, p.expected_sha, "base database")
    manifest: dict = {
        "season": p.season,
        "week": p.week,
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "base_db": {"path": _rel(p.base_db), "sha256_before": base_sha},
        "workdir": _rel(p.workdir),
        "env": p.env,
        "steps": [],
    }
    schedule = p.schedule or (p.workdir / "schedule" / "games_<captured>.parquet")
    steps = build_plan(p, schedule)
    if dry_run:
        manifest["plan"] = [{"step": n, "cmd": c} for n, c in steps]
        return manifest
    copy_sha = fresh_copy(p.base_db, p.db, p.expected_sha)
    manifest["copy"] = {"path": _rel(p.db), "sha256_at_copy": copy_sha}
    if p.schedule is None:
        schedule = capture_schedule(p.workdir / "schedule")
        steps = build_plan(p, schedule)
    manifest["schedule"] = {"path": _rel(schedule), "sha256": sha256_file(schedule)}
    logs = p.workdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **p.env}
    for name, cmd in steps:
        log = logs / f"{name}.log"
        with open(log, "w") as fh:
            rc = subprocess.run(
                cmd, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT
            ).returncode  # noqa: S603
        manifest["steps"].append({"step": name, "cmd": cmd, "exit": rc, "log": _rel(log)})
        print(f"[refresh] {name}: exit {rc}")
        if rc != 0:
            manifest["failed"] = name
            break
    manifest["base_db"]["sha256_after"] = sha256_file(p.base_db)
    if manifest["base_db"]["sha256_after"] != base_sha:
        manifest["failed"] = "base database changed during the refresh"
    manifest["copy"]["sha256_after"] = sha256_file(p.db)
    if "failed" not in manifest:
        snaps = sorted(
            p.out.glob(f"weekly_board_{p.season}_w{p.week:02d}_*.json"), key=os.path.getmtime
        )
        manifest["snapshot"] = _rel(snaps[-1]) if snaps else None
        if p.html and snaps:
            html = p.workdir / f"weekly_board_{p.season}_w{p.week:02d}.html"
            rc = subprocess.run(  # noqa: S603
                [
                    "uv",
                    "run",
                    "python",
                    "scripts/beta/render_board_html.py",
                    str(snaps[-1]),
                    "--out",
                    str(html),
                ],
                cwd=ROOT,
            ).returncode
            manifest["html"] = {"path": _rel(html), "exit": rc}
    manifest["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
    (p.workdir / "refresh_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    if "failed" in manifest:
        raise RefreshError(f"refresh failed at {manifest['failed']}; see {_rel(p.workdir)}/logs")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--base-db", type=Path, default=Path("data/alpha_squad.duckdb"))
    ap.add_argument("--expected-base-sha", default=VERIFIED_BASE_SHA256)
    ap.add_argument(
        "--workdir", type=Path, default=None, help="default data/beta/<season>_wNN_<utc>"
    )
    ap.add_argument("--schedule", type=Path, default=None, help="existing schedule parquet")
    ap.add_argument("--out", type=Path, default=Path("reports/beta"))
    ap.add_argument("--html", action="store_true", help="also render the HTML viewer")
    ap.add_argument("--dry-run", action="store_true", help="verify and print the plan only")
    a = ap.parse_args(argv)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    workdir = a.workdir or BETA_ROOT / f"{a.season}_w{a.week:02d}_{stamp}"
    plan = Plan(
        a.season, a.week, a.base_db, workdir, a.out, a.schedule, a.html, a.expected_base_sha
    )
    try:
        m = run(plan, dry_run=a.dry_run)
    except RefreshError as e:
        print(f"[refresh] REFUSED: {e}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            m if a.dry_run else {k: m.get(k) for k in ("snapshot", "copy", "base_db", "html")},
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
