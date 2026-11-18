# floody

Flood application of `causalflow`: estimate CRS (FEMA Community Rating System) savings
on flood claims and forecast losses/savings for cities under climate scenarios.
General project rules: `../CLAUDE.md`. Tasks: `Plan.md` (here) and `../Plan.md`.

## Code
- `src/floody/data.py`: loaders for FEMA (compiled), PRISM precipitation, CMIP6
  precipitation forecasts, First Street Foundation flood risk, ACS census, ZCTA
  shapefiles; `get_X()` builds the 7 covariates per zipcode for 2022/2030/2040/2052;
  `CityZipcodes()` hard-codes zipcode lists per city.
- `src/floody/floody.py`: `flood_loss()` / `flood_saving()` — load pre-trained Optuna
  flow ensembles and evaluate losses / CRS savings at one covariate vector.
- `bin/data/*.ipynb`: raw → processed data notebooks (provenance of every `floody.*.hdf5`).
- `bin/causalflow/`: `train_causalflow.py` (Optuna training), `hpc.py` (SLURM),
  validation notebooks. `bin/run_floody.py`: per-city loss/saving runs.
- `doc/nb/`: per-city result notebooks (upstream author's; outputs depend on Della files).
- Planned: a CRS-specific subdirectory (location decided in restructuring step), with its
  own CLAUDE.md / Plan.md. floody itself should stay policy-agnostic where reasonable.

## Data
- Processed files (`floody.fema.compiled.hdf5`, `floody.prism.precip.hdf5`,
  `floody.cmip6.precip_forecast.hdf5`, `floody.fsf.floodrisk_forecast.hdf5`,
  `floody.acs_census.hdf5`, `tl_2022_us_zcta520/`) and trained flows are **not in the
  repo**. `_load_data` hard-codes `/Users/chahah/data/noah/` and
  `/scratch/gpfs/chhahn/noah/floody/`; these must become configurable.
- Outcome Y: `paid_claim_per_policy`, trained in **log10**.
- Covariates X (order matters, 7 dims): `mean_monthly_rainfall`, `flood_risk100`,
  `median_household_income` (**log10**), `population` (**log10**), `renter_fraction`,
  `educated_fraction`, `white_fraction`. The log10 transform is applied by the caller
  (copy-pasted in several places), not by `prepare_train_test`.
- Treatment: `CRS_TREAT` boolean.
- `outcome_range` for log10 claims: `[[-1.], [6.]]` in scripts, `[[0.], [6.]]` in
  `bin/causalflow/causalflow.ipynb` — not yet reconciled.
- Monetary results use `transf=lambda x: 10**x` (mean of 10**Y, not 10**mean).
