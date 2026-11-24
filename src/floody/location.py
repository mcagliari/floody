''' Consistency of a claim's reported zipcode with its coordinates and county.

Used for NFIP claims (workspace notebook 08 on the Aug-2020 snapshot; notebook 17 on OpenFEMA v3), but
nothing here is specific to one file: callers pass a table with `zip5` (5-character string), `lat`, `lon`
and `county5` (5-character county FIPS or missing).

- `zcta_points`: 2020 ZCTA internal points and a size-aware distance threshold 3 r + 8 km,
  r = sqrt(land area / pi) (coastal / island ZCTAs get a small r because land area excludes water);
- `zcta_county`: Census 2020 ZCTA-county relationship -> set of (zcta, county) pairs, county -> ZCTAs;
- `far_claims`: distance from each claim's point to its zipcode's ZCTA point; `far` = beyond the threshold;
- `classify_far`: for far claims, `county_ok` (the claim's county is among those its zipcode overlaps) and
  `coords_near_county` (the point is within the threshold of some ZCTA overlapping the claim's county) ->
  class 'coordinates wrong' (county_ok) / 'zipcode wrong' (not county_ok, county known, coords near county) /
  'undecided'.
'''
import numpy as np
import pandas as pd


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2)**2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def zcta_points(shapefile):
    ''' TIGER ZCTA shapefile (2020 ZCTAs) -> DataFrame indexed by `zip5` with zlat, zlon, r_km, thr_km '''
    import pyogrio
    z = pyogrio.read_dataframe(shapefile, columns=['ZCTA5CE20', 'ALAND20', 'INTPTLAT20', 'INTPTLON20'], read_geometry=False)
    z = z.rename(columns={'ZCTA5CE20': 'zip5'})
    z['zlat'] = z['INTPTLAT20'].astype(float)
    z['zlon'] = z['INTPTLON20'].astype(float)
    z['r_km'] = np.sqrt(z['ALAND20'].astype(float) / np.pi) / 1000.
    z['thr_km'] = 3 * z['r_km'] + 8
    return z.set_index('zip5')


def zcta_county(relfile):
    ''' Census 2020 ZCTA-county relationship file -> (set of (zcta, county) pairs, Series county -> list of ZCTAs) '''
    rel = pd.read_csv(relfile, sep='|', dtype=str, usecols=['GEOID_ZCTA5_20', 'GEOID_COUNTY_20']).dropna().drop_duplicates()
    pairs = set(zip(rel['GEOID_ZCTA5_20'], rel['GEOID_COUNTY_20']))
    return pairs, rel.groupby('GEOID_COUNTY_20')['GEOID_ZCTA5_20'].apply(list)


def far_claims(cl, z):
    ''' adds zip_is_zcta, has_coords, d_km, thr_km, far to a copy of `cl` (needs zip5, lat, lon) '''
    cl = cl.copy()
    cl['zip_is_zcta'] = cl['zip5'].isin(z.index)
    cl['has_coords'] = cl['lat'].notna() & cl['lon'].notna()
    ev = cl['zip_is_zcta'] & cl['has_coords']
    zz = z.loc[cl.loc[ev, 'zip5']]
    cl.loc[ev, 'd_km'] = haversine_km(cl.loc[ev, 'lat'].values, cl.loc[ev, 'lon'].values, zz['zlat'].values, zz['zlon'].values)
    cl.loc[ev, 'thr_km'] = zz['thr_km'].values
    cl['far'] = ev & (cl['d_km'] > cl['thr_km'])
    return cl


def classify_far(far, z, pairs, county_zctas):
    ''' far claims (needs zip5, county5, lat, lon) -> copy with county_known, county_ok, coords_near_county, cls '''
    far = far.copy()
    far['county_known'] = far['county5'].isin(county_zctas.index)
    far['county_ok'] = [(zp, ct) in pairs for zp, ct in zip(far['zip5'], far['county5'])]
    far['coords_near_county'] = False
    need = far['county_known'] & ~far['county_ok']
    out = pd.Series(False, index=far.index[need])
    for ct, g in far[need].groupby('county5'):
        zs = z.loc[[x for x in county_zctas[ct] if x in z.index]]
        d = haversine_km(g['lat'].values[:, None], g['lon'].values[:, None], zs['zlat'].values[None, :], zs['zlon'].values[None, :])
        out.loc[g.index] = (d <= zs['thr_km'].values[None, :]).any(axis=1)
    far.loc[need, 'coords_near_county'] = out
    far['cls'] = 'undecided'
    far.loc[far['county_ok'], 'cls'] = 'coordinates wrong'
    far.loc[~far['county_ok'] & far['county_known'] & far['coords_near_county'], 'cls'] = 'zipcode wrong'
    return far
