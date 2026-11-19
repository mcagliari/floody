# Plan (floody)

Workspace-level tasks: `../Plan.md`.

## Data
- [ ] User downloads the processed (or raw) data. Decide the location (outside the
      repos, e.g. a git-ignored data dir) and how code finds it (env var / config),
      replacing the hard-coded paths in `data._load_data` and `floody.py`.

## Known bugs (found by reading the code; not yet reproduced)
- [ ] `flood_saving` loads `support.control` for **both** `support_control` and
      `support_treated` (`src/floody/floody.py`) → treated support is never checked.
- [ ] Impact of the `forecast_latlon` fix (swapped bilinear weights, fixed and verified
      2026-11-19, `docs/lessons.md`): existing city results `floody.<city>.v0*.hdf5` used
      the old weights. Measure the change in forecast precipitation at city zipcodes
      (criterion first); zipcode points available in `floody.prism.precip.hdf5` (labels
      swapped), ZCTA internal points (used by `run_floody`) still missing.
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
