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
- [ ] CRS-specific subdirectory: choose its location (package submodule vs. project
      folder with notebooks), give it its own CLAUDE.md / Plan.md.
- [ ] `flood_loss` / `flood_saving`: stop reloading flows on every call; take model
      paths as arguments.
- [ ] Reconcile `outcome_range` (`[-1, 6]` vs `[0, 6]` in log10 claims).
- [ ] Modelling question (not a bug): training uses the rainfall of the month of loss,
      while forecasts use the max monthly precipitation of the year. Discuss.
