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
- **Local copy (2026-11-18): workspace `data/floody/`** (git-ignored, outside the repos):
  all processed `floody.*.hdf5` files, `ACS2016_20new.csv`, per-city result files
  `floody.<city>.v0[_worst].hdf5`. Missing: the trained flows/supports.
  **`tl_2022_us_zcta520/`** (downloaded by the user 2026-11-19, unzipped to
  `data/floody/tl_2022_us_zcta520/`): Census TIGER/Line 2022 shapefile of 2020-census ZIP
  Code Tabulation Areas, `https://www2.census.gov/geo/tiger/TIGER2022/ZCTA520/tl_2022_us_zcta520.zip`
  (URL as proposed in session; file metadata dated 2022-09-29). 33,791 ZCTAs (= the PRISM
  zipcode-point count), EPSG:4269 (NAD83 lon/lat), polygons + `ZCTA5CE20` (string, leading
  zeros), `ALAND20`/`AWATER20` (m²), `INTPTLAT20`/`INTPTLON20` (internal point, strings).
  Used by `read_zipshape` → `run_floody` interpolates the CMIP6 forecast at the internal
  points. ZCTA ≠ USPS ZIP (block-based approximation; PO-box/single-entity ZIPs have none). `floody.fema.compiled.hdf5` has 74,288 rows (same count as the
  Cano file) with `ZIPCODE`, `YEAROFLOSS`, `MONTHOFLOSS`, lat/lon, `CRS_TREAT`,
  `CRS_SCORE`; no community column.
- Checked 2026-11-18 (workspace `notebooks/02_cano_data.ipynb` §5–6): `fema.compiled` is the
  Cano & Hahn file **row for row, same order** (outcome + 7 covariates agree 100%), plus
  identifiers. Built by `bin/data/fema_compiled.ipynb` from Hahn's
  `zipcode.fema.fsf.acs.rainfall.csv` (received 2026-11-19 with a `.v2` variant, both in
  `data/floody/`; v2 has 4 extra white-fraction columns; compared in workspace notebook 04): `CRS_SCORE` = Cano's
  `communityRatingSystemDiscount` (looks like the CRS class, 11 = not in CRS, non-integer
  values = averaged); `CRS_TREAT` = that CSV's `crs_treat` cast to bool. It differs from
  Cano's "treated = score ≠ 11" on 2,083 rows (all with score in [10, 11)).
  **`crs_treat` rule (notebook 04 §4, pre-registered, supported):** mean over the row's
  claims of "CRS class ≤ 9" (a real discount; class 10 = in CRS, no discount); 4,052 rows
  (5.5%) are fractional = mixed rows. So floody `CRS_TREAT` = "≥ 1 claim with a discount",
  Cano = "≥ 1 claim in a CRS community" (class 10 included).
  Upstream CSVs (notebook 04 §1–2): v2 = v1 + 4 white-fraction columns, otherwise
  identical; **v2 is the source of `fema.compiled`** (all 15 columns 100%, same order). `latitude`/`longitude` have NaNs; if coordinates are needed later and no other
  file has them, derive them from `ZIPCODE` (e.g. ZCTA centroids).
  Structure (2026-11-19, notebook 02 §7): one row = one (zipcode, year, month), no
  duplicates; 14,729 zipcodes, 2004–2020; rows per zipcode median 3, max 69 (only months
  with claims appear — inference). Flood-risk + census covariates are **static per
  zipcode** (the §4 value-proxy coincides exactly with `ZIPCODE`): within a zipcode only
  rainfall, outcome and treatment vary. Years are fairly even (largest 2011, 9.2% of rows).
  ~1,500 zipcodes switch arm over time (both treatment definitions).
  **What a row is** (from the upstream CSV header + 3 sample rows printed in
  `bin/data/fema_compiled.ipynb`): an aggregate of NFIP claim records (OpenFEMA field
  names) per (zipcode, year, month); `amountPaidOnTotalClaim_per_policy` =
  `amountPaidOnTotalClaim` / `policyCount` (checked on the 3 rows) = payout per claimed
  policy, i.e. loss severity *given* a claim, not per policy in force. `primaryResidence`
  (0.667) and the CRS column look averaged over the claims → non-integer CRS values
  (7.5% of rows) = claims from communities of different class mixed in one row
  (inference). The aggregation code is not in the repos.
  Far rows (notebook 02 §9, 2026-11-19): 248 rows (0.33%) lie > 100 km from their zipcode
  (PRISM zipcode points; median row distance 4.9 km). Types seen: leading-zero zipcode
  loss (NE properties under TX/OK/NE zipcodes, e.g. 77581 ↔ 07758; post-hoc 13/18),
  NJ zipcodes with Jersey-Shore locations in Sandy (mailing address? guess), and bad
  coordinates with a plausible zipcode (75638 → South China Sea). Handling: user decision.
  Notebook 04 §3: for informative one-location far rows, `state` follows the location in
  13/32 (all NE storm-month cases incl. the leading-zero ones → zipcode wrong) and the
  zipcode in 18/32 (coordinates wrong, or `state` derived from the zipcode — undecidable);
  verdict "mixed". Size-aware rule (§9 step 3): distance > 3 r + 8 km (r from ACS land
  area, sq mi → km²) flags 672 rows (0.90%), incl. all 248 > 100 km; new ones cluster in
  storm months (Sandy, Ivan, Katrina, Irene/Lee). Decision: flag + exclude by default.
  lat/lon in `fema.compiled` are per row (rounded to 0.1°, differ between rows of one
  zipcode), from the claims; 25 rows NaN.
  Other inputs (structure looked at 2026-11-19, contents not checked):
  `floody.acs_census.hdf5` = 32,713 zipcodes × (income, population, renter, educated,
  white) from `ACS2016_20new.csv` (ACS 5-year 2016–2020 export, built by
  `bin/data/census.ipynb`). Checked (notebook 03 §1): the training census covariates are
  **identical** to it on all 14,729 training zipcodes (none missing), despite the upstream
  CSV labelling them `2018.*`. `get_X` uses the same values for every forecast year
  (census held fixed to 2052 — modelling choice, not a bug).
  `floody.prism.precip.hdf5`: `ZIPCODE` + one point per zipcode (33,791, all FEMA zipcodes;
  likely 2020-ZCTA centroids) — **labels swapped: `lat` holds longitudes, `long` latitudes**
  (unused by code); plus yearly precipitation columns.
  `floody.cmip6.precip_forecast.hdf5` = 28,800 lat/lon grid points × `precip.<year>.<month>`
  (every year 2022–2052) × 36 CMIP6 models, mm/month (×30·86400); the committed
  `forecast_precip.ipynb` writes only 2022/2030/2035/2040/2052 → local file made by a
  different version. City result files `floody.<city>.v0[_worst].hdf5`: per-zipcode
  forecast inputs (2022, 2052) + `flood_loss`/`crs_saving` (± sig), no zipcode column;
  rows = `read_zipshape(CityZipcodes(city))` order (static covariates match 100%).
  **Interpolation-bug impact (notebook 03 §2c, 2026-11-19, pre-registered, "supported"):**
  the old method at ZCTA internal points reproduces every stored `precip.2052` (< 1e-4);
  fixed − old, median |Δ|/σ_models (spread of the 36 CMIP6 models): "average" (`v0`)
  0.02–0.10 in all 7 cities → negligible; "max" (`v0_worst`) 0.77–0.99 → material in
  Houston, Cape Coral, LA (+127 mm/month median), NYC; Chicago 0.04 (§2d, descriptive, no
  stored file: Miami 0.52, New Orleans 0.43; raw CMIP6 node maps in §2d). So `v0_worst`
  losses/savings rest on wrong inputs; `v0` inputs are fine. PRISM zipcode points ≈ ZCTA
  internal points (median offset ~0.001°, 24/611 city zipcodes > 0.01°; all of those
  still reproduce, so the offset is PRISM's, not Hahn's points).
  Additive vs multiplicative change (notebook 03 §2e, descriptive): "average" (get_X
  structure) differs by ≤ 0.21 σ_models median (≤ 6% relative) in all cities; "max" with
  equal 5-yr windows (PRISM 2018–22; models 2022–26 → 2048–52) mostly small but LA −17%
  and NYC +66% (additive 105 vs multiplicative 176 mm/month, because the models' baseline
  max 484 > future max 341): 5-yr pooled maxima are noisy (future max below baseline max).
  `flood_risk100` = First Street 2022 `risk100` per zipcode (one static value per zipcode),
  whereas Cano uses `avg_risk_score_all` (= `flood_risk_avg_score`).
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
