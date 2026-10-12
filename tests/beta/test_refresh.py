"""W16: the one-command beta refresh (`scripts/beta/refresh.py`).

What it must guarantee, independent of any real data:

- it refuses a base database whose hash is not the verified W10 base, before copying anything;
- it always works on a fresh, hash-verified copy and never writes the base;
- A2's row-order restore runs after `features build` and before `train established`;
- it can never write into a holdout path (`data/wNN/`, `reports/weekly/`).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.beta import refresh as rf

pytestmark = pytest.mark.unit


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake repository root holding a tiny 'base database' file."""
    monkeypatch.setattr(rf, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "data" / "alpha_squad.duckdb"
    base.parent.mkdir(parents=True)
    payload = b"verified-base-bytes"
    base.write_bytes(payload)
    sched = tmp_path / "sched.parquet"
    sched.write_bytes(b"schedule")
    return tmp_path, base, _sha(payload), sched


def _plan(base, sha, sched, workdir="data/beta/2026_w06_t", out="reports/beta"):
    return rf.Plan(
        2026, 6, Path("data/alpha_squad.duckdb"), Path(workdir), Path(out), sched, False, sha
    )


def test_verified_base_constant_is_the_d125_hash():
    assert rf.VERIFIED_BASE_SHA256 == (
        "fa8e32dbbb8942d890d38f0fad5c88981dc7f171238826abf13eb09ddd2a73c7"
    )


def test_wrong_base_hash_is_refused_before_any_copy(repo):
    root, base, sha, sched = repo
    p = _plan(base, "0" * 64, sched)
    with pytest.raises(rf.RefreshError, match="sha256"):
        rf.run(p)
    assert not (root / "data" / "beta").exists()


def test_missing_base_is_refused(repo):
    root, base, sha, sched = repo
    base.unlink()
    with pytest.raises(rf.RefreshError, match="not found"):
        rf.run(_plan(base, sha, sched))


@pytest.mark.parametrize(
    ("workdir", "out"),
    [
        ("data/w14/beta", "reports/beta"),  # holdout data dir
        ("data/w17", "reports/beta"),
        ("data/beta", "reports/beta"),  # the beta root itself, not a fresh subdirectory
        ("data/other", "reports/beta"),  # outside data/beta
        ("data/beta/x", "reports/weekly"),  # holdout artifacts
        ("data/beta/x", "reports/weekly/beta"),
        ("data/beta/x", "data/w16/out"),
    ],
)
def test_separation_refuses_holdout_paths(repo, workdir, out):
    root, base, sha, sched = repo
    with pytest.raises(rf.RefreshError):
        rf.check_separation(Path(workdir), Path(out), Path("data/alpha_squad.duckdb"))


def test_separation_accepts_beta_paths(repo):
    rf.check_separation(
        Path("data/beta/2026_w06"), Path("reports/beta"), Path("data/alpha_squad.duckdb")
    )


def test_plan_order_puts_a2_between_features_and_train(repo):
    root, base, sha, sched = repo
    m = rf.run(_plan(base, sha, sched), dry_run=True)
    names = [s["step"] for s in m["plan"]]
    assert names == ["ingest", "identity", "features", "row_order_A2", "train", "board"]
    a2 = m["plan"][3]["cmd"]
    assert "scripts/research/w14_row_order.py" in a2
    assert a2[a2.index("--canonical") + 1] == "data/alpha_squad.duckdb"
    assert a2[a2.index("--db") + 1] == "data/beta/2026_w06_t/alpha_squad_beta.duckdb"
    assert m["env"] == {
        "ALPHA_SQUAD_DB_PATH": "data/beta/2026_w06_t/alpha_squad_beta.duckdb",
        "ALPHA_SQUAD_DATA_DIR": "data/beta/2026_w06_t",
    }
    # dry run touches nothing
    assert not (root / "data" / "beta").exists()


def test_fresh_copy_refuses_an_existing_destination(repo):
    root, base, sha, sched = repo
    dest = root / "data" / "beta" / "x" / "alpha_squad_beta.duckdb"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"stale")
    with pytest.raises(rf.RefreshError, match="fresh copy"):
        rf.fresh_copy(base, dest, sha)


def test_full_run_copies_verifies_and_never_writes_the_base(repo, monkeypatch):
    root, base, sha, sched = repo
    calls = []

    def fake_run(cmd, cwd=None, env=None, stdout=None, stderr=None):
        calls.append((cmd, env))
        # a misbehaving step that writes the copy (allowed) must not reach the base
        Path(root / env["ALPHA_SQUAD_DB_PATH"]).write_bytes(b"ingested")
        if "scripts/beta/weekly_board.py" in cmd:
            out = root / cmd[cmd.index("--out") + 1]
            out.mkdir(parents=True, exist_ok=True)
            (out / "weekly_board_2026_w06_abc.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(rf.subprocess, "run", fake_run)
    m = rf.run(_plan(base, sha, sched))
    assert m["copy"]["sha256_at_copy"] == sha
    assert m["copy"]["sha256_after"] != sha  # the copy was written, not the base
    assert m["base_db"]["sha256_before"] == m["base_db"]["sha256_after"] == sha
    assert base.read_bytes() == b"verified-base-bytes"
    assert [s["step"] for s in m["steps"]][3] == "row_order_A2"
    assert all(e["ALPHA_SQUAD_DB_PATH"].startswith("data/beta/") for _, e in calls)
    assert m["snapshot"] == "reports/beta/weekly_board_2026_w06_abc.json"
    saved = json.loads((root / "data/beta/2026_w06_t/refresh_manifest.json").read_text())
    assert saved["schedule"]["sha256"] == _sha(b"schedule")


def test_failing_step_stops_the_pipeline_and_raises(repo, monkeypatch):
    root, base, sha, sched = repo
    seen = []

    def fake_run(cmd, cwd=None, env=None, stdout=None, stderr=None):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if "w14_row_order.py" in " ".join(cmd) else 0)

    monkeypatch.setattr(rf.subprocess, "run", fake_run)
    with pytest.raises(rf.RefreshError, match="row_order_A2"):
        rf.run(_plan(base, sha, sched))
    assert not any("train" in c for c in seen[-1:]) and len(seen) == 4


def test_main_returns_nonzero_on_refusal(repo, capsys):
    root, base, sha, sched = repo
    rc = rf.main(["--season", "2026", "--week", "6", "--workdir", "data/w15/x", "--dry-run"])
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err
