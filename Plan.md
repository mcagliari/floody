# Plan (floody)

Workspace-level tasks: `../Plan.md`.

## Next steps (ordered, 2026-11-23)
Facts behind these steps: `CLAUDE.md` § Data ("Raw data and rebuild"). Training source = the Aug-2020
snapshot (user, 2026-11-23); NFIP v3 is used only to fix the snapshot's zipcodes (and, optionally, to
get community numbers for CRS history).
1. [ ] **LOCA2 full extraction** (pilot passed, notebook 09). First: email Pierce (courtesy: ~4,800
       throttled range requests; v20240915 vs v20220519 — what changed, documentation, does it still
       preserve the model change ratio, which version to cite; fallback check only if unanswered,
       criterion first). Add to `RangeReader`: retries with backoff, stop after a few consecutive errors.
       Scope: SSP3-7.0, 92 runs × (historical 1950–2014 + 2015–2044 + 2045–2074), 7 city boxes (+0.25°)
       → `raw-loca2/` with README + checksums of our outputs (~60 GB transferred, ~6.5 h). Other SSPs later.
2. [ ] **Snapshot↔v3 match, second stage** (notebook 11 ambiguous: 89.10% unique 1:1, payout agreement
       99.84%): which key fields changed for the 6.8% without a v3 key; separate the 4.0% snapshot
       duplicates by zipcode/payout. Criterion agreed before any second-stage match.
3. [ ] **Zipcode fix at claim level** (replaces the 3 r + 8 km row mask): FEMA's changed zipcodes (4,632
       matched claims) + block-group check (`censusGeoid` → ZCTA, `raw-census/` block file) for matched
       claims; notebook-08 county classes for unmatched ones; keep / drop / reassign per class. Criterion first.
4. [ ] **Rebuild the rows**: notebook-0 aggregation on the cleaned claims + covariate joins (FSF v1.2,
       PRISM, ACS 2016–20). Reproduction of nb1–4 (→ 74,288 rows) cannot be replayed in full (ACS 2008–12 /
       2012–16 exports missing) → fallback check: the 74,288 rows appear in our notebook-07 output with the
       same claim columns (criterion to agree).
5. [ ] **PRISM**: monthly 4 km 1981–2025, current release → `raw-prism/`; zipcode values recomputed on 2020
       ZCTAs for all years; check against Hahn's 1990–2020 `MEAN` first (criterion first).
6. [ ] **ACS vintage** (user's call): one fixed vintage (2016–20, all columns in hand, = what Hahn used) vs
       per period / newer (Census API by ZCTA).
7. [ ] **Single data-prep function** in floody (workspace Plan §4): Hahn's exact behaviour as a "reproduce"
       mode, fixes as options. Hahn's cleaning is now duplicated in notebooks 10 and 11 → move it there
       (ask the user first).
8. [ ] Optional — **CRS history**: locate the 2006–2016 editions of the CRS community list (Internet
       Archive CDX works from the shell); only needed for community-level treatment or data after 2020.
Gated: extending past 2020 needs a CRS source (v3 lost the class for 86% of matched claims).

## Open questions for Hahn
Check his repo first; ask only what it does not answer. (Former question 1, the CMIP6 file,
is moot: we switch to LOCA2 — decided 2026-11-23.)
1. FSF `Flood Risk Data.csv`: source URL and release; are "current / in 30 years" 2020/2050
   or 2022/2052; why `avg_risk.2022` ≠ Cano's `avg_risk_score_all` (89.6% of zipcodes);
   do zeros in the 1–10 score mean missing.
2. From reading `noah`: why `abs()` of negative payments (FEMA: uncashed, re-issued checks); was
   CRS missing → 11 (= control) intended; was the census vintage in nb4 meant to be per period (code
   uses 2016–20 for all years); the raw NFIP file's download date; how the PRISM zipcode CSV and the
   v2 `white_fraction` were made.
3. `prism_zipcode_20240911.csv`: source/tool, swapped `lat`/`long`, centroids or ZCTA
   internal points.
4. `outcome_range`: `[-1, 6]` (scripts) or `[0, 6]` (`causalflow.ipynb`)?
5. Treatment: why `CRS_TREAT` (class ≤ 9) rather than Cano's score ≠ 11?
6. sbi version of the Della flows (old `made` and `num_blocks`)?
7. Bugs found, for upstream: `flood_saving` loads `support.control` twice; swapped
   bilinear weights in `forecast_latlon`; `_validate` swapped tarp outputs;
   `load_flow_control` (fixed). Interest in PRs?

## Paper: limitations to state
- [ ] **Hurricanes / tropical cyclones** drive the worst floods in Miami, Cape Coral, Houston and
      New Orleans, and are what matters most for a flood study. CMIP6 models fall short of the most
      extreme daily values at Miami (Pierce et al. 2023 attribute it, tentatively, to poorly simulated
      strong hurricanes; workspace ref. [6]); statistical downscaling (LOCA2 or NEX) cannot add what
      the GCM lacks. State it as a limitation of the forecast covariate (projected change in
      hurricane-driven extremes = least reliable part).

- [ ] **Data availability**: claims = OpenFEMA NFIP snapshot (Aug 2020, from Hahn; the current v3
      dataset is public, ref. [8]); FSF v1.2 not open access (ref. [10]); PRISM free with citation
      (ref. [9]); LOCA2 per-model CMIP6 licences (CC BY-SA / BY-NC-SA). State what can be shared
      (zipcode × month aggregates?) after checking the OpenFEMA terms.

## Data
- [ ] FSF `avg_risk.2022` ≠ Cano `avg_risk_score_all` (notebook 05 §4, 89.6% of training
      zipcodes differ, mostly by < 0.1, extremes up to ±10). Find out why (rounding /
      different FSF release / zero = missing) — matters only if the avg score is chosen as
      the flood-risk covariate; Questions for Hahn (2).

## Known bugs (found by reading the code; not yet reproduced)
- [ ] `flood_saving` loads `support.control` for **both** `support_control` and
      `support_treated` (`src/floody/floody.py`) → treated support is never checked.
- [ ] Recompute city predictions — gated on retrained flows and the LOCA2 inputs.
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
- [ ] **Treatment definition** (decision for the user): CRS class missing for 36.7% of raw claims (20–57% per
      year in 2004–2019, notebook 10) and set to 11 (= control) by Hahn; FEMA does not say what missing means;
      v3 cannot fill it. Check whether missing means "not in CRS" (e.g. against the historical CRS lists). Cano "score ≠ 11" vs floody
      `CRS_TREAT` (differ on 2,083 rows, score in [10, 11)). Rule now known (notebook 04
      §4): `crs_treat` = fraction of the row's claims with a discount (class ≤ 9);
      `CRS_TREAT` = fraction > 0. Options: any discount (floody), any CRS membership (Cano),
      majority, drop the 5.5% mixed rows, or the fraction as a continuous treatment
      (Scenario C).
- [ ] **Misplaced rows**: the row mask (3 r + 8 km, decided 2026-11-19) is superseded by the claim-level fix
      (Next steps 3). Notebook 08 (pre-registered, *mixed*): of 14,716 far claims, "coordinates wrong" 65.9%
      look like a coastal-ZCTA threshold artifact (zipcode fine → covariates fine), "zipcode wrong" 29.9% look
      real, undecided 4.1%; 28,261 claims have non-ZCTA zipcodes.
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
        **Reframed 2026-11-23 (postponed until the data can be looked at):** two independent
        axes per SSP — (i) statistic S whose per-model ratio scales PRISM: typical month
        (window mean of monthly totals; stable, but one factor for the whole distribution —
        Pierce 2023 Fig. 11 finds daily extremes rising even where the mean falls) vs heavy
        month (mean of annual maxima / high percentile / window max; closer to floods,
        noisier, needs the same runs in baseline and future); (ii) ensemble position:
        median across models ("average") vs high quantile, e.g. q90 ("worst", user's
        "per scenario" idea), runs averaged within each model first. Up to 4 cells per SSP.
        Compute S from monthly *totals* (LOCA2 monthly files are mean rates: × 86400 × days).
      - **Decided 2026-11-23: use LOCA2** (supersedes NEX-GDDP-CMIP6, 2026-11-20): PresRat keeps each model's
        change ratio, up to 10 runs per model (refs [5]–[7]). Ratio applied to PRISM, not absolute values.
      - Rebuild note: if any input comes as a flux (kg m⁻² s⁻¹), convert with the real
        days per month of the model's calendar (the old `× 30·86400`: Feb +7.1%, 31-day
        months −3.2%).
