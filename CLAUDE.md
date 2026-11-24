# floody

Flood application of `causalflow`: estimate CRS (FEMA Community Rating System) savings
on flood claims and forecast losses/savings for cities under climate scenarios.
General project rules: `../CLAUDE.md`. Tasks: `Plan.md` (here) and `../Plan.md`.

## Code
- `src/floody/data.py`: loaders for FEMA (compiled), PRISM precipitation, CMIP6
  precipitation forecasts, First Street Foundation flood risk, ACS census, ZCTA
  shapefiles; `get_X()` builds the 7 covariates per zipcode for 2022/2030/2040/2052;
  `CityZipcodes()` hard-codes zipcode lists per city. `FEMA.prepare(split_by, val_fraction,
  test_fraction, seed)` (2026-11-20, skeleton of the single data-prep function): Y/X with
  log10 applied, split once on the full table (`causalflow.split.train_val_test`, groups
  from `FEMA.groups`: `random` | `zipcode` | `event` = year·100 + month) then by arm →
  `{'train'|'val'|'test': {'treated'|'control': (Y, X, row_index)}}`. Old
  `prepare_train_test` kept until its notebook callers move.
- `src/floody/loca2.py` (2026-11-23): general reader for LOCA2 monthly files over HTTP byte ranges
  (classic netCDF): `parse_header`, `RangeReader` (multi-range requests, refuses non-206 / oversized
  responses, pause between requests, certificate verification always on), `box_indices`, `merge_bands`,
  `extract_boxes` (full-width latitude bands → boxes, values as stored). Verified bit-for-bit against an
  independent reader (workspace notebook 09). Server facts: files per run × period (historical 1950–2014;
  SSPs 2015–2044 / 2045–2074 / 2075–2100), monthly variable `pr_tavg` (kg m-2 s-1, missing 1e30), grid
  474 × 944 at 1/16°, lon 0–360, `.md5` only for daily files, certificate chain incomplete (CA bundle with
  the SSL.com intermediate in `raw-loca2/`), 200 ranges per request accepted.
  Also (2026-11-24): `LocalReader` (same interface on a downloaded file), `download_file` (one connection,
  resumable, size check, md5), `save_boxes` (output layout of the pilot). Job script `bin/loca2/extract_cities.py`
  (+ `extract_cities.slurm`) for the full extraction on TACC; unit tests `tests/test_loca2.py`.
  Job script behaviour: walks a file list (`url`, `bytes`), skips files whose output exists, downloads one full file
  at a time to `--work-dir`, cuts the boxes, deletes the full file, appends to `extract_log.csv`; stops starting new
  files 15 min before `--time-limit`. Outputs are flat in `--out-dir`, named `<source file>.cities.nc` → historical
  outputs are shared by all SSP lists. Local dry run bit-identical to the pilot (workspace notebook 14 §5).
  The slurm template (LS6 `vm-small`, 2 h) has `-A` as placeholder, conda path to adapt, banner-safe chain commands.
  LS6 facts (2026-11-24): download from the LOCA2 server 14.1 MB/s on a login node, 7.9 MB/s on a compute node;
  writing to `$WORK` much faster than to `$SCRATCH` (user); `vm-small` ≤ 4 running / ≤ 16 submitted jobs per
  user; TACC's `sbatch` prints the login banner to stdout (filter the job id).
  Server: ssp245, ssp370, ssp585 only; ensemble composition differs by SSP (notebook 14 §7).
- `src/floody/floody.py`: `flood_loss()` / `flood_saving()` — load pre-trained Optuna
  flow ensembles and evaluate losses / CRS savings at one covariate vector.
- `bin/data/*.ipynb`: raw → processed data notebooks (provenance of every `floody.*.hdf5`).
- `bin/causalflow/`: `train_causalflow.py` (Optuna training: `flow|support`, arm, study,
  `-d`, `--split-by`, `--split-seed`, `--n-trials`, `--max-epochs` (tests only: sbi does
  not restore the best weights when the cap stops training)); objective = loss on the
  external validation set, sbi's internal loss logged as trial attr `internal_loss`;
  setup stored as study attrs and a resumed study with a different setup is refused;
  `hpc.py` (Della SLURM), validation notebooks. `bin/run_floody.py`: per-city loss/saving runs.
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
  Other inputs (structure looked at 2026-11-19):
  `floody.acs_census.hdf5` = 32,713 zipcodes × (income, population, renter, educated,
  white) from `ACS2016_20new.csv` (ACS 5-year 2016–2020 export, built by
  `bin/data/census.ipynb`). Checked (notebook 03 §1): the training census covariates are
  **identical** to it on all 14,729 training zipcodes (none missing), despite the upstream
  CSV labelling them `2018.*`. `get_X` uses the same values for every forecast year
  (census held fixed to 2052 — modelling choice, not a bug).
  `floody.prism.precip.hdf5`: `ZIPCODE` + one point per zipcode (33,791, all FEMA zipcodes;
  ≈ ZCTA points, median 0.004° from the internal points, 6,654 > 0.01°) — **labels swapped
  in the file (from the raw PRISM CSV): `lat` holds longitudes, `long` latitudes**. Fixed on
  load (2026-11-20): `Precip` renames them to `latitude`/`longitude` by value (|value| > 90 =
  longitude; raises if undecidable), so a corrected file also works. Plus yearly
  precipitation columns.
  **Decided 2026-11-23: forecast precipitation will come from LOCA2** (CMIP6 downscaled
  with LOCA, Pierce et al. 2023; supersedes NEX-GDDP-CMIP6, chosen 2026-11-20; reasons:
  PresRat preserves each model's change ratio, up to 10 members per model — workspace refs
  [5]–[7]); the current
  CMIP6 file below is kept only as the record of Hahn's results. Hahn's preprocessing repo
  (`noah`) and the raw NFIP snapshot are now in hand: see "Raw data and rebuild" below.
  `floody.cmip6.precip_forecast.hdf5` = 28,800 lat/lon grid points × `precip.<year>.<month>`
  (every year 2022–2052) × 36 CMIP6 models, mm/month (×30·86400); 1.5° common grid, so
  regridded by whoever built `cmip6_data.npy` (CMIP6 output is on each model's own grid,
  `grid_label` gn/gr). What a CMIP6 run is (refs [1–3] in workspace `docs/references.md`):
  model (`source_id`) × experiment (`experiment_id`: `historical` 1850–2014, then one
  ScenarioMIP scenario 2015–2100, e.g. `ssp245`) × member (`variant_label` r·i·p·f; future
  runs normally keep the realization of their historical parent). `pr` = monthly-mean
  precipitation flux, kg m⁻² s⁻¹. Unknown for our file: the scenario(s), the member per
  model, the model list, the regridding — ask Hahn. Index from 1850 in
  `forecast_precip.ipynb` fits historical + one scenario spliced (inference). The committed
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
  **FSF file (workspace notebook 05, 2026-11-20, pre-registered):** 31,977 zipcodes, no
  NaN/duplicates, all 14,729 training zipcodes present (25 with `risk100.2022` = 0).
  `risk{5,100,500}` = percent (0–100) of properties flooded in the 5/100/500-yr flood.
  Labels are consistent: nesting 5 ≤ 100 ≤ 500 holds in every zipcode (H1 supported), and
  the `.2052` columns are the larger ones in ~95% of changed zipcodes (H1b consistent;
  median change +0.2–0.3 points). Actual FSF years possibly 2020/2050 (guess, unchecked).
  `avg_risk.2022` (scale 1–10, but min 0 in the file) ≠ Cano's `avg_risk_score_all`: equal
  within 1e-6 in only 10.4% of training zipcodes (H2 verdict "different release"); median
  difference +0.02 (IQR −0.01…+0.08) but extremes −10…+8.4. Cause not established.
- **Raw data and rebuild (2026-11-23).** One folder per source in `$FLOODY_DATA`, each with `README.md`
  (source, URL, date) and `SHA256SUMS`: `raw-fema/` (claims, FSF v1.2, Hahn's PRISM zipcode CSV, ZCTA–county
  file, OpenFEMA field list), `raw-census/` (2020 ZCTA–block file), `raw-loca2/` (CA bundle; `pilot/` city
  boxes; `city_boxes.json`; file lists `filelist_ssp{370,245,585}.csv`, notebook 14; full-run outputs planned in
  `ssp370/`), `raw-prism/` (planned).
  - **Hahn's pipeline** = workspace `noah/` (`changhoonhahn/noah`, read-only): `bin/make_catalog.py::fema_catalog`
    (raw claims → `fema.trimed.csv`: CRS missing → 11; `abs()` of building/contents payments — negative =
    uncashed re-issued checks per FEMA; total paid = building + contents, ICC excluded; keep state present,
    paid > 0, coverage > 0 → outcome = loss per *paid* claim; removes 22.7% of claims as unpaid) → `nb/0`
    (drop missing/odd zipcodes; zipcode × year × month rows; `crs_treat` = mean over claims of class ≤ 9;
    lat/lon = mean of claim coordinates; payouts and `policyCount` summed) → `nb/1` (FSF "Climate Risk
    Statistics" v1.2 zip file → `avg_risk_score_all`, `pct_fs_risk_*`; rows without FSF dropped) → `nb/2`
    (three ACS Social Explorer exports; rows need all three) → `nb/3` (PRISM zipcode × month `MEAN`, 1990–2020;
    10.7% of rows dropped) → `nb/4` (years > 2003; **bug: every period takes the ACS 2016–20 ("2018.")
    columns**). Output = our `zipcode.fema.fsf.acs.rainfall.csv` (v1; v2 adds `white_fraction`, not in the repo).
  - **Snapshot** `raw-fema/fema.csv`: 2,478,927 claims, `asOfDate` ≈ 2020-08-23 (no claims after Aug 2020).
    Reproduced exactly (workspace notebook 07): `fema_catalog` → 1,916,033 rows = `fema.trimed.csv` (all 42
    columns), nb0 → 213,680 rows. CRS class missing for 36.7% of claims. Lat/lon rounded to 0.1°;
    `censusTract` empty. **Training source** (user, 2026-11-23).
  - **NFIP v3** `raw-fema/NfipClaimsV3.parquet` (OpenFEMA, refresh 2026-11-16, 2,731,064 claims; identical to
    the live API on spot checks). Renamed fields (`reportedZipCode`, `crsClassCode`, `censusGeoid` = block
    group, `primaryResidenceIndicator`), integer ids (no join to the snapshot ids). **CRS class lost**: missing
    for 81–98% of 2004–2019 claims (notebook 10); for matched claims, v3 has the class for only 14% of those
    that had one in the snapshot (notebook 11). Role: fix the snapshot's zipcodes (FEMA's corrections; block
    groups) and community numbers (`nfipRatedCommunityNumber`; zero-pad to 6 digits) — not a training source.
  - **v3 `crsClassCode` is not dated** (workspace notebook 13, 2026-11-24, pre-registered): in NFIP policies v3
    (`raw-fema/NfipPoliciesV3.parquet`, 74.8 M records, effective 2009–2026) and v3 claims it is the community's
    *current* class (= OpenFEMA Community Status Book, 99.9%) written onto every record, also before the date that
    class took effect (100% of 136,957 policy months). Neither file is a CRS history. Snapshot class = v3 class for
    only 53% of matched 2009–2019 claims; snapshot claims without a class sit in communities without a class today
    in 94% of cases (descriptive).
  - **Snapshot class is not the class at the date of loss** (workspace notebook 15 §2, 2026-11-24, pre-registered:
    of 94,859 matched claims with loss before their community's CRS entry date (Status Book), only 13.4% lack a
    class; caveat: re-entry dates). Descriptive: it equals the current Status Book class for 99.3% of claims after the
    current class took effect. Inference: a class from around 2020 written onto all claims. → Hahn's/Cano's
    treatment (`crs_treat`, `communityRatingSystemDiscount`) is not dated; a dated treatment needs the CRS lists.
  - Field meanings (OpenFEMA v3 field list, assumed unchanged since 2020): `countyCode` = primary county of
    the project (not geocoded, may differ from the property's county); lat/lon rounded for privacy;
    `reportedZipCode` as reported by the insurer; `crsClassCode` 1–10, missing not defined.
  - Notebook results: 08 (claim-level zipcode/location classes, *mixed*), 10 (v3 vs snapshot rows,
    *ambiguous*; missing rows = 0.12% of claims), 11 (snapshot↔v3 claim match, *ambiguous*: 89.10% unique 1:1,
    payout agreement 99.84%; 4,632 matched claims with a changed zipcode).
  - Historical CRS community lists (class, effective dates) exist as Flood Insurance Manual sections
    (Internet Archive 2002–2005, 2017–2018, fema.gov 2020/2024/2026); OpenFEMA's Community Status Book is
    current-only (class + date it took effect; `raw-fema/NfipCommunityStatusBook.csv`). First Street is not open
    access → keep v1.2.
- Processed files (`floody.fema.compiled.hdf5`, `floody.prism.precip.hdf5`,
  `floody.cmip6.precip_forecast.hdf5`, `floody.fsf.floodrisk_forecast.hdf5`,
  `floody.acs_census.hdf5`, `tl_2022_us_zcta520/`) and trained flows are **not in the
  repo**. Data directory = environment variable **`FLOODY_DATA`** (`data.data_dir()`,
  2026-11-20; error if unset); locally the workspace `data/floody/`. Flow/support paths
  in `floody.py` are still hard-coded to Della (Plan: take model paths as arguments).
- Outcome Y: `paid_claim_per_policy`, trained in **log10**.
- Covariates X (order matters, 7 dims): `mean_monthly_rainfall`, `flood_risk100`,
  `median_household_income` (**log10**), `population` (**log10**), `renter_fraction`,
  `educated_fraction`, `white_fraction`. log10 applied inside `FEMA.prepare`; the old
  `prepare_train_test` leaves it to the caller (copy-pasted in several places).
- Treatment: `CRS_TREAT` boolean.
- `outcome_range` for log10 claims: `[[-1.], [6.]]` in scripts (`OUTCOME_RANGE` in
  `train_causalflow.py`, recorded in the study), `[[0.], [6.]]` in
  `bin/causalflow/causalflow.ipynb` — not yet reconciled.
- Monetary results use `transf=lambda x: 10**x` (mean of 10**Y, not 10**mean).
