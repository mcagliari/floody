# Plan (floody)

Workspace-level tasks: `../Plan.md`.

## Data
- [ ] User downloads the processed (or raw) data. Decide the location (outside the
      repos, e.g. a git-ignored data dir) and how code finds it (env var / config),
      replacing the hard-coded paths in `data._load_data` and `floody.py`.

## Known bugs (found by reading the code; not yet reproduced)
- [ ] `flood_saving` loads `support.control` for **both** `support_control` and
      `support_treated` (`src/floody/floody.py`) → treated support is never checked.
- [ ] Rerun city predictions with the fixed interpolation — gated on trained flows (Hahn's
      are not available locally and are old-sbi pickles; retraining gated on workspace
      §3b/§4). Priority: the `v0_worst` ("max") results, whose inputs moved materially
      (notebook 03 §2c); `v0` ("average") inputs barely moved.
- [ ] `CityZipcodes()` lists contain duplicates (Cape Coral: 35 entries, 28 unique =
      rows of `floody.capecoral.v0.hdf5`): find where they are dropped; check other lists.

## Restructuring (gated on workspace step 3)
- [ ] `bin/causalflow/validate_flow.ipynb`: `_validate` now needs `outcome_range` and
      returns `(alpha, ecp)` correctly (workspace Plan §3a); update the calls. Its old
      plots were reflected about the diagonal (swapped TARP outputs).
- [ ] CRS-specific subdirectory: choose its location (package submodule vs. project
      folder with notebooks), give it its own CLAUDE.md / Plan.md.
- [ ] `flood_loss` / `flood_saving`: stop reloading flows on every call; take model
      paths as arguments.
- [ ] **Treatment definition** (decision for the user): Cano "score ≠ 11" vs floody
      `CRS_TREAT` (differ on 2,083 rows, score in [10, 11)). Rule now known (notebook 04
      §4): `crs_treat` = fraction of the row's claims with a discount (class ≤ 9);
      `CRS_TREAT` = fraction > 0. Options: any discount (floody), any CRS membership (Cano),
      majority, drop the 5.5% mixed rows, or the fraction as a continuous treatment
      (Scenario C).
- [ ] **Misplaced rows — decided 2026-11-19: flag and exclude by default.** Rule
      (notebook 02 §9 step 3, verdict "use the size-aware rule"): distance to zipcode point
      > 3 r + 8 km (r = √(land area/π) from ACS) → 672 rows (0.90%), superset of the
      248 rows > 100 km. Implement as a general mask function in `floody/src/floody/data.py`
      (PRISM zipcode points with swapped labels fixed, ACS land area), used by the single
      data-prep function; keep k as a parameter for sensitivity (k = 2/5 → 783/533 rows).
      Same row order → same mask for the Cano dataset. Long term: rebuild rows from raw
      NFIP claims (aggregation code still to get from Hahn).
- [ ] **Flood-risk covariate**: Cano `avg_risk_score_all` vs floody `flood_risk100`
      (static FSF 2022 per zipcode) — choose and document.
- [ ] Reconcile `outcome_range` (`[-1, 6]` vs `[0, 6]` in log10 claims).
- [ ] Modelling question (not a bug): training uses the rainfall of the month of loss,
      while forecasts use the max monthly precipitation of the year. Discuss.
- [ ] Modelling question: **how the forecast precipitation covariate is built**
      (`get_X`, `data.py:219-247`; notebook 03 §2c–2d, 2026-11-19). Points to decide:
      - "average": delta change (additive), baseline = single year 2022 on both sides
        (PRISM observed vs CMIP6 2022, which is not synchronised with real weather), target =
        single year 2052 per model → weather noise in both ends. Options: multi-year
        windows (PRISM has yearly columns from 1990; CMIP6 file has 2022–2052),
        multiplicative (ratio) change instead of additive.
      - "max": raw CMIP6 level (no PRISM anchoring) → different spatial scale from the
        PRISM training covariate; max taken after interpolation dilutes extremes when nodes
        peak in different model-months (NYC: all zipcodes below the lowest node max).
        Option: anchor like "average" (PRISM 2022 max + CMIP6 worst − CMIP6 2022 max), or
        quantile-based correction.
      - Position effect: cities near an interpolation-cell centre (Chicago) get ≈ the
        4-node mean; 1.5° grid cannot resolve intra-city structure (any method).
      - **Direction agreed 2026-11-19:** multiplicative (ratio) change for both scenarios,
        worst case scaled too: per model, PRISM statistic × (model future / model
        baseline), then ensemble median + spread. Same window length and statistic on
        observed and model sides (a max grows with sample size; no pooling over models).
        To decide at rebuild: window lengths, "average" statistic, "worst" definition
        (window max vs percentile/return level). Additive vs multiplicative differ by
        (O − M₀)(M₁/M₀ − 1). Measured (notebook 03 §2e): negligible for "average";
        large for "max" in LA/NYC, where 5-yr pooled maxima are noisy (NYC future max <
        baseline max) → use longer windows and/or per-model percentiles for "worst".
      - Feasible with the current file: ratio change for both scenarios (PRISM-anchored),
        multi-year windows (model baseline can only start 2022 — no historical runs),
        per-model worst case + ensemble median/spread. Not feasible: true bias correction.
      - Alternative inputs (checked 2026-11-19): NEX-GDDP-CMIP6 v2 (NASA; 0.25°, daily
        1950–2100 incl. historical, 35 models, 4 SSPs, BCSD vs GMFD, CC0, public S3
        `nex-gddp-cmip6` + THREDDS box subsetting) and CMIP6-LOCA2 (1/16°, CONUS, 27 models,
        SSP2-4.5/3-7.0/5-8.5, Livneh-based; per USGS NCCV doc — loca.ucsd.edu unreachable,
        TLS). Use as ratio applied to PRISM (training basis), not absolute (inference).
      - Ask Hahn: which SSP/ensemble the local CMIP6 file holds (not in the repo), and for
        the source `cmip6_data.npy` (models × months × lat × lon, indexed from 1850 in
        `bin/data/forecast_precip.ipynb` → likely historical + scenario) with its model
        list. Would give a historical baseline for the same 36 models, still 1.5°.
        Rebuild note: `× 30·86400` assumes 30-day months (±3% error).
