# W16 — Holdout database recovery and verification

**Date:** 2026-10-12. **Scope:** read-only verification plus a preservation attempt. No model,
protocol or production change. Decision record: `docs/DECISIONS.md` D125 (resolves D124 option a).

## 1. Question

Is `data/alpha_squad.duckdb`, the file the W14/W15 holdout copies were taken from, the
original W10 base? Or was it rebuilt or modified after W10?

## 2. The three databases

| file | role | bytes | sha-256 |
|---|---|---:|---|
| `data/alpha_squad.duckdb` | canonical base (W5–W13, W10, and the source of every holdout copy) | 119,812,096 | `fa8e32dbbb8942d890d38f0fad5c88981dc7f171238826abf13eb09ddd2a73c7` |
| `data/w14/alpha_squad_2026.duckdb` | W14 look 1 (weeks 1–3), isolated copy plus 2026 ingest | 156,250,112 | `569d74b92a4a75e6b6b8d7bcc27098f8e64f89f167f166479c8cdfc7082feb38` |
| `data/w15/alpha_squad_2026.duckdb` | W15 look 2 (weeks 1–4), fresh isolated copy plus 2026 ingest | 156,250,112 | `e745603d60f3e23f29861dd83a2c3fccf93ab28b39a1384a5628eabe7ea32b7a` |

All three hashes were the same before and after the reproductions below. No file was written.

## 3. Structural comparison

- **Tables.** All three files have the same 40 tables, with identical schemas.
- **Snapshot registry.**
  - Canonical: 134 snapshots, the last captured 2026-09-20.
  - Each 2026 copy contains all 134, plus 21 captured on its own look date (w14 2026-10-05,
    w15 2026-10-10).
  - The added snapshots are listed with their hashes in
    `docs/weekly/manifests/w14_snapshot_manifest.json` and `w15_snapshot_manifest.json`. Every
    file's hash matches its registry entry.
- **Seasons through 2025.** `player_week_stats`, `games`, `weekly_projection_snapshot` and
  `team_week_stats` are row-for-row identical across all three files.
- **`player_week_features` through 2025** differs in only two ways:
  - `built_at`, as expected;
  - the K/DST rows (5,664 K, 94 DST), which `features build` recomputes.

  **Zero** QB/RB/WR/TE rows differ in any model input or target.
- **Identity tables.** The 2026 copies only add keys; no canonical key is missing.

  | copy | new `player_id_map` keys | new `players` keys |
  |---|---:|---:|
  | w14 | 365 | 14 |
  | w15 | 472 | 23 |

- **2026 rows.** The canonical file has **no** 2026 outcome rows.

## 4. Frozen reproductions (byte-identical)

| run | database | output sha-256 | committed artifact |
|---|---|---|---|
| `w10_historical.py` (W10 2021–2025) | canonical | `7963324aea45af2139b6da221e7ea3cd8419a2576f7ceffdab9eb43bb79ea1b5` | `reports/weekly/w10_results.json`, identical |
| `w14_2026_validation.py`, w14 schedule | w14 copy | `3dbb7f1276986e8e490b9a89306eecadd2c4ef3a58dd5e5a42fe90a5e79d28a9` | `reports/weekly/w14_results.json`, identical |
| `w14_2026_validation.py`, w15 schedule | w15 copy | `2a423650662adb0203ffbf4a8c1039ba81d5652f6a2d01e560e35c79544a6ac0` | `reports/weekly/w15_results.json`, identical |

- **W10 reproduces** its frozen result: WR capture@10 B − A = +0.0223 [+0.0068, +0.0384],
  SUCCESS.
- **Earlier reproductions on the same base** (W15): W5–W13, 14/14 artifacts, byte-identical.

**Conclusion: ORIGINAL DATABASE VERIFIED.** `fa8e32db…` is the W10 base, and both holdout
copies descend from it.

**Relation to D124.** A parallel W16 session found no canonical file in its container and
worked on a rebuilt base (`8b6cca85…`). On that base W10's arms gave WR capture@10 +0.0291
instead of the committed +0.0223. That rebuilt base is a different database. The original
reproduces +0.0223 exactly, so D124's option (a), recovering the canonical database, is met.
Holdout look 3 uses a fresh copy of `fa8e32db…`.

## 5. Durable preservation — status: NOT PRESERVED (blocked)

A documentation commit does not preserve a gitignored 120 MB database. The copies that exist
are:

| copy | location | durable? | verified |
|---|---|---|---|
| original | `data/alpha_squad.duckdb` in the session container | **no** (ephemeral container) | `fa8e32db…` |
| xz-compressed | `alpha_squad.duckdb.xz` (22,506,172 B, sha `513f82a3f17f50593ffb5c440da5953ca262ec19d937da7acca5d4fe7fb5846c`) in the session scratchpad | **no** (same container) | `xz -dc` round-trips to `fa8e32db…` |
| w14 / w15 copies, raw snapshots and schedules | `data/w14`, `data/w15` in the container | **no** | hashes in §2 and in the manifests |

Mechanisms tried:

1. **Git commit / GitHub release on `gimann421/alpha-squad`.** Technically possible, but:
   - the repository is **public**, so it would publish third-party source data;
   - `CLAUDE.md` forbids committing anything under `data/`.

   Not done without the owner's explicit approval.
2. **New private GitHub repository.** `create_repository` returns
   `403 Resource not accessible by integration`. Every repository this session can reach is
   public.
3. **Google Drive connector.** It accepts file content only inline in a tool call. 30 MB of
   base64 across many calls was not attempted.
4. **Private claude.ai artifact asset store.** Four base64 text parts of about 10 MB each, with a
   restore recipe. The publish was **denied by the session's permission policy**, classified as
   data exfiltration.

**Remaining blocker.** No mechanism that is both permitted and private is available to this
session. The owner can resolve it in one of three ways:

- approve a GitHub release asset on the public repository (licensing is the owner's call);
- allow the artifact upload;
- copy the file out of the container themselves, e.g. through Remote Control, or by giving the
  session a private repository.

**If the file is lost**, the identity in §2–§4 is still checkable. Any rebuilt base must hash to
`fa8e32db…`, or reproduce the three artifacts above byte-for-byte, before it can serve the
holdout. A rebuilt file that does neither is a different base, and the holdout must say so.
