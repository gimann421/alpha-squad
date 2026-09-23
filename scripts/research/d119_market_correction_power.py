"""D119 -- is D118's market-vs-model signal strong enough to justify ONE controlled draft-decision
experiment? A pre-registered power analysis, and a gate the experiment cannot pass without it.

Read-only research runner. Reads D118's artifact (`d118_measured.json`, `d118_summary.json`) and
D115's `arms` artifacts re-run on the same vintage (`d115_arms.json`, one per format), and writes
nothing but JSON under `--out`. **No file under `src/alpha_squad/` is touched and this script is
imported by no production path.**

    uv run python scripts/research/d119_market_correction_power.py --mode power \
        --d118 <dir> --arms <t>/d115_arms.json --arms <d>/d115_arms.json --out <out>
    uv run python scripts/research/d119_market_correction_power.py --mode experiment --out <out>

==========================================================================================
PRE-REGISTRATION -- written before any D119 number existed
==========================================================================================

THE FROZEN TREATMENT (nothing is tuned; every quantity comes from D118 as committed)
-------------------------------------------------------------------------------------
    corrected_proj(i, S) = proj(i, S) + beta_S[cohort] * z_mkt_vs_model(i, S)

  * `z_mkt_vs_model` is D118's own feature: the player's within-(season, position) projection
    rank minus his ECR rank, z-scored within (season, position). It is read from D118's artifact.
  * `beta_S[cohort]` is D118's univariate walk-forward ridge slope (alpha = 1.0, per-position
    intercepts, trained on 2021..S-1 only), refitted here with D118's own `fit_ridge` and CHECKED
    against D118's stored predictions to 1e-9. Established and rookie cohorts keep separate slopes,
    exactly as D118 fitted them.
  * The INTERCEPT IS DROPPED. D118's intercepts are per-position means of past residuals; keeping
    them would shift whole positions against each other, which is D68's closed positional-
    calibration question, not this signal. Without the intercept the correction is mean-zero
    within every (season, position), so it can only re-order players WITHIN a position. Within a
    position, D118's prediction differences equal the correction differences exactly (the
    intercept cancels), so D118's measured flip rate, flip accuracy and gain per flip ARE this
    treatment's within-position properties, with no approximation.
  * NO THRESHOLD. The correction is continuous, so small disagreements move nothing and large
    ones can re-order. A threshold would need a value chosen from data, which is tuning.
  * 2021 has no prior season inside the window, so its correction is exactly 0 and treatment
    equals control there. The experiment's effective sample is **2022-2025, k = 4 seasons**.
  * Players outside D118's panel (K, DST, anyone without a preseason ECR rank) get 0.
  * Insertion point: `load_season_static(projections_override=...)`, the same single point D68's
    X-arms use, so MSV, VORP, replacement levels and every derived term see one consistent board.
  * Control: production Alpha (SHIPPED_TIER on the unmodified board). Everything else identical.

THE POWER MODEL (inputs are D118's pre-registered results and D115's EXISTING arms only)
-----------------------------------------------------------------------------------------
Estimand: D114/D115's one-step matched-state effect per pick (the treatment chooses the pick at
each audited production state; a common shipped continuation scores both), per format, season-
clustered. Per format the grid is 64 picks per season (4 slots x 16 rounds).

  per-pick effect       E = p_c * g
      p_c  share of picks the treatment changes;  g  mean one-step value per changed pick
  season-mean SD        sd_season(p_c) = infl * sigma_c * sqrt(64 * p_c) / 64
      sigma_c  SD of one-step delta on a changed pick -- read from D115's EXISTING arms on this
               vintage (X2, X3, FP_ECR_Y1, L1), which is the roster-outcome noise any arm faces
      infl     observed between-season SD / pure-sampling SD of those same arms (season-level
               heterogeneity the sampling formula misses)
  SE = sd_season / sqrt(4);  95% CI half-width = t(.975, 3) * SE  (this repo's "MDE", D114)
  80%-power MDE: the smallest true effect detected with 80% power by a two-sided t test, df = 3,
  from the noncentral t. Power at any true effect from the same.
  The variance model is CHECKED leave-one-arm-out: each existing arm's observed k = 5 half-width
  is predicted from its own changed rate and sigma_c with the OTHER arms' mean inflation (using
  its own inflation would reproduce it by construction, which is no check at all).

  Inputs from D118 (established cohort, `mkt_vs_model`, the signal actually frozen here):
    observed flip rate      share of same-position pairs whose order the correction reverses
                            (ECR <= 200: all pairs, and close pairs |proj gap| <= 30)
    observed flip accuracy  share of flips that match the realized order
    observed gain per flip  realized raw points gained per flip, with its season CI
    upper-bound recovery    D118's regret share on flipped sequencing pairs (hindsight-selected)
  These are pairwise statistics. A pick is not a pair, so p_c is a SCENARIO, never a point
  estimate: lower = D118's all-pair flip share; central = its close-pair flip share (picks are
  decided among close candidates); ceiling = the changed-pick rate of the most aggressive
  market-based arm that exists (FP_ECR_Y1, which replaces the ordering outright). g is D118's
  gain per flip in RAW points, taken at face value -- generous, because D114 measured raw points
  converting to roster value at 0.109 for market-driven changes (and D115 at 1.22 for the
  oracle's); a 1.0 conversion is assumed and labelled optimistic.

SMALLEST PRACTICALLY INTERESTING EFFECT (SPIE), per format, from D118 alone
---------------------------------------------------------------------------
  SPIE = D118's upper-bound regret share on the sequencing population x the format's mean per-
  pick regret. That is the MOST this signal was shown able to reach, on the population selected
  in its favour; an effect smaller than it is not interesting, and a design that cannot see it
  cannot see anything this signal could plausibly do.

DECISION RULE (fixed now)
-------------------------
  GO   only if, in the PRIMARY format (target_league), the CONSERVATIVE case (infl = the largest
       observed; sigma_c = the pooled observed; p_c = central; g = D118 point estimate) has
       >= 80% power at the SPIE. D114's ~13-point resolution is reported as context and is NOT
       used as a threshold: the design's own MDE is what decides.
  NO-GO otherwise. A GO-favourable case (infl = 1, p_c = ceiling, g = the top of D118's CI) is
       reported beside it, so a NO-GO that survives even that is a robust NO-GO.
  On NO-GO the experiment mode REFUSES to run and the line is closed. No weights, thresholds or
  alternative corrections are tried afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb
import numpy as np
from scipy import optimize
from scipy import stats as scipy_stats

from alpha_squad.evaluation.board_vintage import compute_board_vintage

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
PRIMARY_FORMAT = "target_league"
PICKS_PER_SEASON = 64  # 4 slots x 16 rounds, D103/D115's grid
K_SEASONS = 4  # 2022-2025; 2021 is structurally zero
ALPHA_LEVEL = 0.05
TARGET_POWER = 0.80
D114_RESOLUTION = 13.0  # context only, never a threshold
COMPARABLE_ARMS = ("X2", "X3", "FP_ECR_Y1", "L1")
SIGNAL = "mkt_vs_model"
EFFECT_GRID = (0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 20.0)


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D118 = _load("d118_upside_predictability")


class UnreconstructibleError(RuntimeError):
    """D119 stops rather than substituting."""


class NoGoError(RuntimeError):
    """The pre-registered power gate said NO-GO; the experiment does not run."""


# --------------------------------------------------------------------------------------------
# Power mathematics -- pure functions
# --------------------------------------------------------------------------------------------
def t_crit(k: int, alpha: float = ALPHA_LEVEL) -> float:
    return float(scipy_stats.t.ppf(1 - alpha / 2, k - 1))


def season_sd(p_c: float, sigma_c: float, infl: float, n: int = PICKS_PER_SEASON) -> float:
    """SD of a season's mean per-pick delta when a share p_c of n picks change, each with delta
    SD sigma_c, inflated by the observed between-season heterogeneity factor."""
    if p_c <= 0:
        return 0.0
    return infl * sigma_c * math.sqrt(n * p_c) / n


def standard_error(p_c: float, sigma_c: float, infl: float, k: int = K_SEASONS) -> float:
    return season_sd(p_c, sigma_c, infl) / math.sqrt(k)


def power(effect: float, se: float, k: int = K_SEASONS, alpha: float = ALPHA_LEVEL) -> float:
    """Two-sided t test on k season means: P(|T| > t_crit) with T ~ noncentral t(k-1, d/SE)."""
    if se <= 0:
        return 1.0 if effect != 0 else alpha
    # Power is symmetric in the sign of the effect, so work with |nc|. scipy's noncentral-t CDF
    # returns NaN once the far (wrong-sign) tail underflows; that tail is then 0 to machine
    # precision, which the Monte Carlo check in the tests confirms.
    df, tc, nc = k - 1, t_crit(k, alpha), abs(effect) / se
    near = float(scipy_stats.nct.sf(tc, df, nc))
    far = float(scipy_stats.nct.cdf(-tc, df, nc))
    return min(1.0, near + (0.0 if math.isnan(far) else far))


def mde_at_power(se: float, k: int = K_SEASONS, target: float = TARGET_POWER) -> float:
    """Smallest true effect with `target` power (exact, noncentral t)."""
    if se <= 0:
        return 0.0
    return float(optimize.brentq(lambda d: power(d, se, k) - target, 1e-9, 20 * se))


def ci_half_width(se: float, k: int = K_SEASONS) -> float:
    """This repository's 'MDE' (D114): the 95% CI half-width."""
    return t_crit(k) * se


# --------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------
def arm_variance(arm_rows: list[dict]) -> dict:
    """sigma_c, observed between-season SD, pure-sampling SD and inflation for EXISTING arms."""
    out = {}
    for arm in COMPARABLE_ARMS:
        r = [x for x in arm_rows if x["arm"] == arm]
        if not r:
            continue
        changed = [x["delta"] for x in r if x["changed"]]
        per_season = defaultdict(list)
        for x in r:
            per_season[x["season"]].append(x["delta"])
        means = [mean(v) for _, v in sorted(per_season.items())]
        n_per = mean(len(v) for v in per_season.values())
        p_c = len(changed) / len(r)
        sigma_c = stdev(changed) if len(changed) > 1 else 0.0
        observed_btw = stdev(means) if len(means) > 1 else 0.0
        sampling = sigma_c * math.sqrt(n_per * p_c) / n_per
        out[arm] = {
            "n": len(r),
            "changed_rate": p_c,
            "sigma_c": sigma_c,
            "mean_delta_changed": mean(changed) if changed else None,
            "per_season_mean": means,
            "observed_between_season_sd": observed_btw,
            "pure_sampling_sd": sampling,
            "inflation": observed_btw / sampling if sampling else None,
            "observed_half_width_k5": t_crit(len(means)) * observed_btw / math.sqrt(len(means)),
        }
    return out


def frozen_slopes(panel: list[dict], stored_preds: dict) -> dict:
    """D118's univariate walk-forward slope for SIGNAL per (cohort, season), refitted with D118's
    own fit_ridge and checked against D118's stored predictions."""
    slopes: dict = {}
    for cohort in D118.COHORT_FEATURES:
        rows = [r for r in panel if r["cohort"] == cohort]
        stored = stored_preds[cohort]["A"][SIGNAL]
        for season in D118.OOS_SEASONS:
            train = [r for r in rows if r["season"] < season]
            test = [r for r in rows if r["season"] == season]
            if not train or not test:
                continue
            x = np.array([[r[f"z_{SIGNAL}"]] for r in train])
            y = np.array([r["e"] for r in train], dtype=float)
            coef, b0 = D118.fit_ridge(x, y, [r["position"] for r in train])
            pred = D118.predict_ridge(
                coef,
                b0,
                np.array([[r[f"z_{SIGNAL}"]] for r in test]),
                [r["position"] for r in test],
            )
            for r, p in zip(test, pred, strict=True):
                want = stored[f"{r['player_id']}|{r['season']}"]
                if abs(p - want) > 1e-9 * max(1.0, abs(want)):
                    raise UnreconstructibleError(
                        f"refit does not reproduce D118's prediction for {r['player_id']} {season}"
                    )
            corr = [float(coef[0]) * r[f"z_{SIGNAL}"] for r in test]
            dec = [c for r, c in zip(test, corr, strict=True) if r["ecr_rank"] <= 200]
            slopes[f"{cohort}|{season}"] = {
                "beta": float(coef[0]),
                "n": len(test),
                "sd_correction": stdev(corr) if len(corr) > 1 else 0.0,
                "mean_abs_correction_ecr200": mean(abs(c) for c in dec) if dec else None,
                "max_abs_correction": max(abs(c) for c in corr),
            }
    return slopes


def d118_inputs(summary: dict) -> dict:
    """The observed pairwise statistics of the frozen signal, from D118's committed summary."""
    out = {}
    for label in ("ECR<=200", "ALL"):
        m = summary["cohorts"]["established"][f"oos_{label}"][SIGNAL]
        da, dc = m["decision_all"], m["decision_close"]
        out[label] = {
            "flip_rate_all_pairs": da["flipped"] / da["pairs"],
            "flip_rate_close_pairs": dc["flipped"] / dc["pairs"],
            "flip_accuracy": da["flips_correct"] / da["flipped"],
            "gain_per_flip": m["gain_per_flip"],
            "gain_per_flip_ci": m["gain_per_flip_ci"]["ci"],
            "ordering_accuracy_proj": m["ordering_accuracy_proj"],
            "ordering_accuracy_adjusted": m["ordering_accuracy_adjusted"],
            "oos_rho": m["signed"]["mean"],
        }
    return out


def spie(summary: dict, regret_totals: dict, n_picks: dict) -> dict:
    """Smallest practically interesting effect per format: D118's upper-bound regret share on the
    sequencing pairs flipped by the frozen signal (same + cross position) x mean regret/pick."""
    out = {}
    for league, total in regret_totals.items():
        seq = summary["sequencing"][league][SIGNAL]
        flipped = seq["same"]["regret_flipped"] + seq["cross"]["regret_flipped"]
        share = flipped / total
        out[league] = {
            "upper_bound_share_of_regret": share,
            "mean_regret_per_pick": total / n_picks[league],
            "spie_points_per_pick": share * total / n_picks[league],
        }
    return out


def scenarios(inputs: dict, var: dict) -> dict:
    """The three pre-registered cases."""
    ecr = inputs["ECR<=200"]
    sig = [v["sigma_c"] for v in var.values()]
    infl = [v["inflation"] for v in var.values() if v["inflation"]]
    ceiling = var.get("FP_ECR_Y1", {}).get("changed_rate", 0.6)
    g_top = ecr["gain_per_flip_ci"][1] if ecr["gain_per_flip_ci"] else ecr["gain_per_flip"]
    return {
        "conservative": {
            "p_c": ecr["flip_rate_close_pairs"],
            "g": ecr["gain_per_flip"],
            "sigma_c": mean(sig),
            "infl": max(infl),
        },
        "central_low_leverage": {
            "p_c": ecr["flip_rate_all_pairs"],
            "g": ecr["gain_per_flip"],
            "sigma_c": mean(sig),
            "infl": mean(infl),
        },
        "go_favourable": {
            "p_c": ceiling,
            "g": g_top,
            "sigma_c": min(sig),
            "infl": 1.0,
        },
    }


def evaluate_case(case: dict, spie_pts: float, flip_accuracy: float) -> dict:
    se = standard_error(case["p_c"], case["sigma_c"], case["infl"])
    expected = case["p_c"] * case["g"]
    treatable = PICKS_PER_SEASON * K_SEASONS
    changed = case["p_c"] * treatable
    return {
        **case,
        "expected_changed_picks": changed,
        "expected_correct_changes": flip_accuracy * changed,
        "expected_incorrect_changes": (1 - flip_accuracy) * changed,
        "expected_effect_per_pick": expected,
        "expected_effect_per_draft": expected * 16,
        "season_sd": season_sd(case["p_c"], case["sigma_c"], case["infl"]),
        "se": se,
        "variance_of_estimate": se**2,
        "ci_half_width": ci_half_width(se),
        "mde_80": mde_at_power(se),
        "power_at_expected": power(expected, se),
        "power_at_spie": power(spie_pts, se),
        "power_grid": {str(d): power(d, se) for d in EFFECT_GRID},
        # ANTI-CONSERVATIVE sensitivity, never the decision basis: the 16 drafts of 2022-2025 as
        # independent units (16 picks each), no season inflation. It ignores that drafts in one
        # season share a board, so it overstates power -- which is the point: a NO-GO that
        # survives it does not hinge on the clustering choice.
        "draft_clustered_anticonservative": _draft_clustered(case, spie_pts),
    }


def _draft_clustered(case: dict, spie_pts: float, drafts: int = 16, picks: int = 16) -> dict:
    sd = season_sd(case["p_c"], case["sigma_c"], 1.0, n=picks)
    se = sd / math.sqrt(drafts)
    return {
        "k": drafts,
        "se": se,
        "mde_80": mde_at_power(se, k=drafts),
        "power_at_spie": power(spie_pts, se, k=drafts),
        "power_at_expected": power(case["p_c"] * case["g"], se, k=drafts),
    }


def validate_variance_model(var: dict) -> dict:
    """LEAVE-ONE-ARM-OUT check of the season-SD model. Feeding an arm its OWN inflation would
    reproduce its half-width by construction (inflation is defined as that ratio), so each arm is
    predicted with the MEAN inflation of the OTHER arms. The model is usable if those predictions
    land near the observed half-widths."""
    out = {}
    for arm, v in var.items():
        others = [w["inflation"] for a, w in var.items() if a != arm and w["inflation"]]
        infl = mean(others) if others else 1.0
        predicted = t_crit(5) * season_sd(v["changed_rate"], v["sigma_c"], infl) / math.sqrt(5)
        out[arm] = {
            "inflation_from_other_arms": infl,
            "predicted_hw5": predicted,
            "observed_hw5": v["observed_half_width_k5"],
            "ratio_observed_to_predicted": v["observed_half_width_k5"] / predicted
            if predicted
            else None,
        }
    return out


def _src_tree() -> dict:
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()

    return {
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "src_tree_hash_at_head": run(["git", "rev-parse", "HEAD:src/alpha_squad"]),
        "src_dirty": bool(run(["git", "status", "--porcelain", "--", "src/alpha_squad"])),
    }


def run_power(con, d118_dir: Path, arm_paths: list[Path]) -> dict:
    vintage = compute_board_vintage(con).combined_hash
    measured = json.loads((d118_dir / "d118_measured.json").read_text())
    summary = json.loads((d118_dir / "d118_summary.json").read_text())
    if measured["provenance"]["board_vintage_combined"] != vintage:
        raise UnreconstructibleError("D118 artifact and database are different vintages")
    arms: dict = {}
    hashes = {}
    for path in arm_paths:
        payload = json.loads(path.read_text())
        if payload["provenance"]["board_vintage_combined"] != vintage:
            raise UnreconstructibleError(f"{path} is a different vintage")
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for league in {r["league"] for r in payload["rows"]}:
            arms[league] = [r for r in payload["rows"] if r["league"] == league]
    if set(arms) != set(FORMATS):
        raise UnreconstructibleError(f"need D115 arms for both formats, have {sorted(arms)}")

    slopes = frozen_slopes(measured["panel"], measured["preds"])
    inputs = d118_inputs(summary)
    regret_totals = measured["regret_totals"]
    n_picks = {lg: len([r for r in arms[lg] if r["arm"] == "Y1"]) for lg in FORMATS}
    spie_by = spie(summary, regret_totals, n_picks)
    formats: dict = {}
    for league in FORMATS:
        var = arm_variance(arms[league])
        cases = scenarios(inputs, var)
        formats[league] = {
            "arm_variance": var,
            "variance_model_check": validate_variance_model(var),
            "spie": spie_by[league],
            "cases": {
                name: evaluate_case(
                    c, spie_by[league]["spie_points_per_pick"], inputs["ECR<=200"]["flip_accuracy"]
                )
                for name, c in cases.items()
            },
        }
    primary = formats[PRIMARY_FORMAT]["cases"]["conservative"]
    decision = "GO" if primary["power_at_spie"] >= TARGET_POWER else "NO-GO"
    return {
        "treatment": {
            "definition": "proj + beta_S[cohort] * z_mkt_vs_model; intercept dropped; no threshold; "
            "2021 = 0; K/DST/no-ECR = 0",
            "slopes": slopes,
        },
        "d118_inputs": inputs,
        "formats": formats,
        "decision": decision,
        "decision_basis": {
            "format": PRIMARY_FORMAT,
            "case": "conservative",
            "power_at_spie": primary["power_at_spie"],
            "required": TARGET_POWER,
            "spie": spie_by[PRIMARY_FORMAT]["spie_points_per_pick"],
            "d114_resolution_context_only": D114_RESOLUTION,
        },
        "provenance": {
            "board_vintage_combined": vintage,
            "d118_measured_sha256": hashlib.sha256(
                (d118_dir / "d118_measured.json").read_bytes()
            ).hexdigest(),
            "d118_summary_sha256": hashlib.sha256(
                (d118_dir / "d118_summary.json").read_bytes()
            ).hexdigest(),
            "d115_arms_sha256": hashlib.sha256(
                json.dumps(hashes, sort_keys=True).encode()
            ).hexdigest(),
            "d115_arms_files": hashes,
            "argv": sys.argv,
            **_src_tree(),
        },
    }


def print_report(res: dict) -> None:
    bar = "=" * 100
    print(
        f"{bar}\nD119 POWER ANALYSIS -- frozen treatment: {res['treatment']['definition']}\n{bar}"
    )
    for k, s in sorted(res["treatment"]["slopes"].items()):
        print(
            f"  slope {k:<18} beta {s['beta']:+7.2f} pts/SD  sd(corr) {s['sd_correction']:5.1f}  "
            f"mean|corr| ECR<=200 {s['mean_abs_correction_ecr200'] or 0:5.1f}  max {s['max_abs_correction']:5.1f}"
        )
    print("\n  D118 inputs (established, mkt_vs_model):")
    for label, v in res["d118_inputs"].items():
        print(f"    {label}: {json.dumps(v, default=str)}")
    for league, f in res["formats"].items():
        print(f"\n{bar}\n{league}\n{bar}")
        for arm, v in f["arm_variance"].items():
            chk = f["variance_model_check"][arm]
            print(
                f"  existing arm {arm:<10} changed {v['changed_rate']:.3f} sigma_c {v['sigma_c']:5.1f} "
                f"btwSD {v['observed_between_season_sd']:5.2f} sampling {v['pure_sampling_sd']:5.2f} "
                f"infl {v['inflation']:.2f}  hw5 obs {chk['observed_hw5']:.2f} leave-one-out model "
                f"{chk['predicted_hw5']:.2f}"
            )
        sp = f["spie"]
        print(
            f"  SPIE: upper-bound share {sp['upper_bound_share_of_regret']:.2%} x mean regret "
            f"{sp['mean_regret_per_pick']:.1f} = {sp['spie_points_per_pick']:.2f} pts/pick"
        )
        for name, c in f["cases"].items():
            print(
                f"  [{name}] p_c {c['p_c']:.3f} g {c['g']:+.1f} sigma_c {c['sigma_c']:.1f} infl "
                f"{c['infl']:.2f} | changed {c['expected_changed_picks']:.0f}/256 (correct "
                f"{c['expected_correct_changes']:.0f}, wrong {c['expected_incorrect_changes']:.0f}) | "
                f"E {c['expected_effect_per_pick']:+.2f}/pick ({c['expected_effect_per_draft']:+.1f}/draft) | "
                f"SE {c['se']:.2f} CI+- {c['ci_half_width']:.2f} MDE80 {c['mde_80']:.2f} | "
                f"power@E {c['power_at_expected']:.3f} power@SPIE {c['power_at_spie']:.3f}"
            )
            dc = c["draft_clustered_anticonservative"]
            print(
                f"      anti-conservative (16 drafts, no inflation): SE {dc['se']:.2f} MDE80 "
                f"{dc['mde_80']:.2f} power@SPIE {dc['power_at_spie']:.3f} power@E "
                f"{dc['power_at_expected']:.3f}"
            )
            print(
                "      power grid: " + "  ".join(f"{d}:{p:.2f}" for d, p in c["power_grid"].items())
            )
    print(f"\n{bar}\nDECISION: {res['decision']}  basis {res['decision_basis']}\n{bar}")


def _write(out: Path, name: str, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    print(f"wrote {out / name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("power", "experiment"))
    ap.add_argument("--d118", help="directory holding d118_measured.json and d118_summary.json")
    ap.add_argument("--arms", action="append", default=[], help="D115 d115_arms.json per format")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if a.mode == "power":
        if not a.d118 or len(a.arms) != 2:
            raise UnreconstructibleError("--d118 and two --arms files are required")
        con = duckdb.connect(a.db, read_only=True)
        res = run_power(con, Path(a.d118), [Path(p) for p in a.arms])
        print_report(res)
        _write(out, "d119_power.json", res)
        return
    # --mode experiment: the gate. It reads the pre-registered power artifact and refuses to run
    # the treatment unless that artifact says GO.
    res = json.loads((out / "d119_power.json").read_text())
    if res["decision"] != "GO":
        raise NoGoError(
            f"pre-registered power gate is {res['decision']} "
            f"(power at SPIE {res['decision_basis']['power_at_spie']:.3f} < "
            f"{res['decision_basis']['required']}); the frozen experiment does not run"
        )
    raise UnreconstructibleError(
        "the gate says GO but the frozen arm is not implemented in this runner; implement it as "
        "specified in the pre-registration before running -- do not improvise"
    )


if __name__ == "__main__":
    main()
