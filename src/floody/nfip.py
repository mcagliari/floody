''' NFIP claims: Hahn's selection (workspace `noah/`), on the raw OpenFEMA claims of either version.

Reproduces `noah/bin/make_catalog.py::fema_catalog` (raw claims -> `fema.trimed.csv`) and the zipcode filters of
`noah/nb/0` (moved here 2026-11-24 from workspace notebooks 10 / 11 / 08; counts reproduced). Field names of the
Aug-2020 snapshot (OpenFEMA v1) and of v3 are both accepted (`V3_TO_V1`). Each step is returned as its own flag
so a notebook can show what every cut removes; the selection may change after the step-by-step review (floody
Plan, Next steps 7).

Steps, in Hahn's order:
1. `has_state`  : `state` present;
2. `paid_ok`    : building + contents paid > 0 (each `abs()`: negative = uncashed, re-issued check; missing -> 0;
                  increased-cost-of-compliance payments excluded);
3. `covered`    : building + contents coverage > 0 (missing -> 0);
   (1-3 = `fema_catalog`; CRS class missing -> 11 there, i.e. counted as "not in CRS" -- kept as `crs_missing`)
4. `zip_ok`     : notebook 0 — zipcode present and not one of the "weird" values (77571 in NJ, 0, 99999).
`kept` = all four.
'''
import numpy as np
import pandas as pd

V3_TO_V1 = {'reportedZipCode': 'reportedZipcode', 'crsClassCode': 'communityRatingSystemDiscount',
            'primaryResidenceIndicator': 'primaryResidence', 'ratedFloodZone': 'floodZone'}
COLUMNS = ['reportedZipcode', 'state', 'yearOfLoss', 'dateOfLoss', 'communityRatingSystemDiscount', 'policyCount',
           'amountPaidOnBuildingClaim', 'amountPaidOnContentsClaim', 'totalBuildingInsuranceCoverage',
           'totalContentsInsuranceCoverage']                    # v1 names; for v3 files read the V3_TO_V1 keys
STEPS = ['has_state', 'paid_ok', 'covered', 'zip_ok']


def _num(s):
    return pd.to_numeric(s.replace('', np.nan) if s.dtype == object else s, errors='coerce')


def weird_zip(zip_num, state):
    ''' notebook 0's "weird" zipcodes: 77571 reported in NJ, 0, 99999 '''
    return ((zip_num == 77571) & (state == 'NJ')) | (zip_num == 0) | (zip_num == 99999)


def zip_filter(zip_num, state):
    ''' notebook 0's zipcode filter: zipcode present and not weird '''
    return zip_num.notna() & ~weird_zip(zip_num, state)


def hahn_selection(df):
    ''' raw claims (snapshot or v3 field names) -> DataFrame on the same index with
    zip (int, leading zeros lost as in Hahn), state, year, month, crs (missing -> 11), crs_missing, policyCount,
    paid, coverage, the step flags (`STEPS`) and `kept`. '''
    df = df.rename(columns=V3_TO_V1)
    out = pd.DataFrame(index=df.index)
    out['zip'] = _num(df['reportedZipcode'].astype(object).where(df['reportedZipcode'].notna(), np.nan))
    out['state'] = df['state'].replace('', np.nan)
    out['year'] = _num(df['yearOfLoss'])
    out['month'] = pd.to_datetime(df['dateOfLoss'].astype(str).str[:10], errors='coerce').dt.month
    crs = _num(df['communityRatingSystemDiscount'])
    out['crs_missing'] = crs.isna()
    out['crs'] = crs.fillna(11)
    out['policyCount'] = _num(df['policyCount'])
    b = _num(df['amountPaidOnBuildingClaim']).abs().fillna(0)
    c = _num(df['amountPaidOnContentsClaim']).abs().fillna(0)
    out['paid'] = b + c
    out['coverage'] = _num(df['totalBuildingInsuranceCoverage']).fillna(0) + _num(df['totalContentsInsuranceCoverage']).fillna(0)
    out['has_state'] = out['state'].notna()
    out['paid_ok'] = out['paid'] > 0
    out['covered'] = out['coverage'] > 0
    out['zip_ok'] = zip_filter(out['zip'], out['state'])
    out['kept'] = out['has_state'] & out['paid_ok'] & out['covered'] & out['zip_ok']
    return out


def selection_table(sel):
    ''' claims left after each step, in Hahn's order '''
    m = pd.Series(True, index=sel.index)
    rows = [('raw claims', len(sel))]
    for f, label in [('has_state', 'state present'), ('paid_ok', 'paid > 0'), ('covered', 'coverage > 0'),
                     ('zip_ok', 'zipcode present, not weird (notebook 0)')]:
        m &= sel[f]
        rows.append((label, int(m.sum())))
    return pd.DataFrame(rows, columns=['after step', 'claims'])
