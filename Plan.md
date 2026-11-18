# Plan (floody)

Workspace-level tasks: `../Plan.md`.

## Data
- [ ] User downloads the processed (or raw) data. Decide the location (outside the
      repos, e.g. a git-ignored data dir) and how code finds it (env var / config),
      replacing the hard-coded paths in `data._load_data` and `floody.py`.

## Known bugs (found by reading the code; not yet reproduced)
- [ ] `flood_saving` loads `support.control` for **both** `support_control` and
      `support_treated` (`src/floody/floody.py`) → treated support is never checked.
- [ ] `Forecast.forecast_latlon`: bilinear weights look swapped (each corner gets the
      opposite corner's weight). Unverified inference — check numerically on a known
      field before changing.

## Restructuring (gated on workspace step 3)
- [ ] `bin/causalflow/validate_flow.ipynb`: `_validate` now needs `outcome_range` and
      returns `(alpha, ecp)` correctly (workspace Plan §3a); update the calls. Its old
      plots were reflected about the diagonal (swapped TARP outputs).
- [ ] CRS-specific subdirectory: choose its location (package submodule vs. project
      folder with notebooks), give it its own CLAUDE.md / Plan.md.
- [ ] `flood_loss` / `flood_saving`: stop reloading flows on every call; take model
      paths as arguments.
- [ ] **Treatment definition** (decision for the user): Cano "score ≠ 11" vs floody
      `CRS_TREAT` (differ on 2,083 rows, score in [10, 11), i.e. CRS class 10 / averaged).
      Rule behind `CRS_TREAT` unknown (upstream CSV) and not a threshold on the score
      (notebook 02 §6). Possibly ask Hahn / Cano how `crs_treat` was built.
- [ ] **Flood-risk covariate**: Cano `avg_risk_score_all` vs floody `flood_risk100`
      (static FSF 2022 per zipcode) — choose and document.
- [ ] Reconcile `outcome_range` (`[-1, 6]` vs `[0, 6]` in log10 claims).
- [ ] Modelling question (not a bug): training uses the rainfall of the month of loss,
      while forecasts use the max monthly precipitation of the year. Discuss.
