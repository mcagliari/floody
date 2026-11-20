# Plan (floody)

Workspace-level tasks: `../Plan.md`.

## Next session (agreed with Hahn, 2026-11-20 — user's meeting)
- [ ] **Hahn's preprocessing repo** (shared with the user: the notebooks that built our
      processed files). User clones it; decide where (inside the workspace, git-ignored
      like the forks?). Then read it against our open data issues: NFIP aggregation and
      per-row lat/lon (misplaced rows), `crs_treat`, PRISM points and swapped labels, FSF
      source/release and `avg_risk` vs Cano, `outcome_range`.
- [ ] **Plan the NEX-GDDP-CMIP6 download** (replaces the current CMIP6 file for the
      forecast precipitation, see Modelling questions): which models and scenarios, period
      (historical baseline + future), domain (CONUS; AK/HI/PR?), daily → monthly
      aggregation, storage size, where (local / TACC), access (S3 vs THREDDS subsetting),
      provenance (version, file list, checksums).
- Gated: **Hahn looks for the original FEMA (NFIP) data.** If found, rebuild the processed
  dataset from the raw claims, cleaning zipcode/location problems at the source; this may
  replace the misplaced-row mask (Restructuring) and settle `crs_treat`.

## Open questions for Hahn
Check his repo first; ask only what it does not answer. (Former question 1, the CMIP6 file,
is moot: we switch to NEX-GDDP-CMIP6.)
1. FSF `Flood Risk Data.csv`: source URL and release; are "current / in 30 years" 2020/2050
   or 2022/2052; why `avg_risk.2022` ≠ Cano's `avg_risk_score_all` (89.6% of zipcodes);
   do zeros in the 1–10 score mean missing.
2. NFIP aggregation (claims → zipcode × month rows), where the per-row lat/lon come from,
   `crs_treat` = share of claims with class ≤ 9? (notebook 04 §4).
3. `prism_zipcode_20240911.csv`: source/tool, swapped `lat`/`long`, centroids or ZCTA
   internal points.
4. `outcome_range`: `[-1, 6]` (scripts) or `[0, 6]` (`causalflow.ipynb`)?
5. Treatment: why `CRS_TREAT` (class ≤ 9) rather than Cano's score ≠ 11?
6. sbi version of the Della flows (old `made` and `num_blocks`)?
7. Bugs found, for upstream: `flood_saving` loads `support.control` twice; swapped
   bilinear weights in `forecast_latlon`; `_validate` swapped tarp outputs;
   `load_flow_control` (fixed). Interest in PRs?

## Data
- [ ] FSF `avg_risk.2022` ≠ Cano `avg_risk_score_all` (notebook 05 §4, 89.6% of training
      zipcodes differ, mostly by < 0.1, extremes up to ±10). Find out why (rounding /
      different FSF release / zero = missing) — matters only if the avg score is chosen as
      the flood-risk covariate; Questions for Hahn (2).

## Known bugs (found by reading the code; not yet reproduced)
- [ ] `flood_saving` loads `support.control` for **both** `support_control` and
      `support_treated` (`src/floody/floody.py`) → treated support is never checked.
- [ ] Recompute city predictions — gated on retrained flows and the NEX-GDDP-CMIP6 inputs.
      Hahn's `v0`/`v0_worst` results are superseded (old CMIP6 file; `v0_worst` inputs
      also hit by the interpolation bug, notebook 03 §2c).
- [ ] `CityZipcodes()` lists contain duplicates (Cape Coral: 35 entries, 28 unique =
      rows of `floody.capecoral.v0.hdf5`): find where they are dropped; check other lists.

## Restructuring (gated on workspace step 3)
- [ ] Move the remaining callers of `FEMA.prepare_train_test` to `FEMA.prepare`, then
      remove it: `bin/causalflow/{causalflow,validate_flow,validate_support}.ipynb`,
      `doc/nb/support.ipynb` (Hahn's, Della paths). Studies are now journal files
      (`causalflow.study`); Hahn's SQLite studies hold old-sbi pickles anyway.
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
      Same row order → same mask for the Cano dataset. May be superseded: if Hahn finds
      the raw NFIP data, the rows are rebuilt and cleaned at the source (Next session).
- [ ] **Flood-risk covariate**: Cano `avg_risk_score_all` vs floody `flood_risk100`
      (static FSF 2022 per zipcode) — choose and document. `risk100` labels checked
      (notebook 05: nesting and future > current hold); the avg score differs from Cano's
      (see Data).
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
      - **Decided 2026-11-20 (with Hahn): use NEX-GDDP-CMIP6** instead of the current
        CMIP6 file (documented models × scenarios × members, historical runs for a real
        baseline). Download planned next session. Inputs checked 2026-11-19: NEX-GDDP-CMIP6 v2 (NASA; 0.25°, daily
        1950–2100 incl. historical, 35 models, 4 SSPs, BCSD vs GMFD, CC0, public S3
        `nex-gddp-cmip6` + THREDDS box subsetting) and CMIP6-LOCA2 (1/16°, CONUS, 27 models,
        SSP2-4.5/3-7.0/5-8.5, Livneh-based; per USGS NCCV doc — loca.ucsd.edu unreachable,
        TLS). Use as ratio applied to PRISM (training basis), not absolute (inference).
      - Rebuild note: if any input comes as a flux (kg m⁻² s⁻¹), convert with the real
        days per month of the model's calendar (the old `× 30·86400`: Feb +7.1%, 31-day
        months −3.2%).
