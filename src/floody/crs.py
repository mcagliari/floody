"""CRS (Community Rating System) class history per community.

Built from the CRS lists of the NFIP Flood Insurance Manual (one table per edition, parsed in workspace notebook 16
into ``raw-crs/crs_lists_all.csv``) and the OpenFEMA Community Status Book (current class only). Rules agreed
2026-11-25 (floody ``Plan.md`` item 8):

1. each full-list row gives a change point (effective date, class); class at t = class of the latest change point <= t;
2. before the CRS entry date: not in CRS, class 10;
3. between the entry date and the earliest change point: in CRS, class unknown (flag ``unknown``);
4. dates inside a gap between consecutive list dates longer than ``GAP_DAYS``: flag ``gap``;
5. communities in no list: class 10;
6. partial lists (no dates) are not used to build;
7. the Status Book adds its (class, effective date) when that date is after the last full list.

Class 10 = no discount (not in CRS, or in CRS with class 10 / rescinded).
"""
import numpy as np
import pandas as pd

GAP_DAYS = 214          # > 7 months between consecutive list dates -> 'gap'
NOT_IN_CRS = 10


def read_lists(path):
    """``crs_lists_all.csv`` (notebook 16) with community as 6-character string and dates parsed."""
    t = pd.read_csv(path, dtype={'community': str, 'list_date': str})
    for c in ['entry_date', 'effective_date', 'as_of']:
        t[c] = pd.to_datetime(t[c])
    return t


def read_status_book(path):
    """OpenFEMA ``NfipCommunityStatusBook.csv``: community (zero-padded to 6), ``cls`` (NaN = no class),
    ``entry_date``, ``effective_date`` (naive dates)."""
    b = pd.read_csv(path, dtype=str)
    out = pd.DataFrame({'community': b['communityIdNumber'].str.zfill(6),
                        'cls': pd.to_numeric(b['classRating'], errors='coerce')})
    for new, old in [('entry_date', 'originalEntryDate'), ('effective_date', 'classRatingEffectiveDate')]:
        out[new] = pd.to_datetime(b[old], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
    out['last_refresh'] = pd.to_datetime(b['lastRefresh'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
    return out


def full_list_dates(lists):
    """Sorted ``as_of`` dates of the full (not partial) lists."""
    return np.sort(lists.loc[~lists['partial'], 'as_of'].unique())


def _override(history, community, from_date, add):
    """Drop ``community``'s change points on or after ``from_date`` and append ``add`` (DataFrame of change points)."""
    keep = ~((history['community'] == community) & (history['from_date'] >= from_date))
    return pd.concat([history[keep], add], ignore_index=True)


def crs_history(lists, status_book=None, set_class=(), follow=()):
    """Change points per community.

    Per-community fixes (decided case by case, e.g. floody ``Plan.md`` item 8 rule 8), applied after rules 1 and 7
    (``set_class`` first, so a follower also gets the fixes of the community it follows); each replaces the
    community's change points from its date on:

    - ``set_class``: ``(community, from_date, cls)`` — class ``cls`` from ``from_date`` on (source ``'fix'``);
    - ``follow``: ``(community, other, from_date)`` — from ``from_date`` on, the class of community ``other``
      (source ``'follow <other>'``), e.g. a community absorbed by another one.

    Returns ``(history, entry)``:

    - ``history``: one row per (community, ``from_date``) with ``cls`` (class from that date on), ``first_list`` and
      ``last_list`` (first/last list showing it; ``'status_book'`` for rule 7) and ``n_classes`` (> 1 = lists disagree
      on the class for this effective date; the class of the latest list is kept);
    - ``entry``: one row per community with ``entry_date`` (earliest entry date over the full lists; Status Book entry
      date for communities added by rule 7 only) and ``n_entry_dates`` (distinct entry dates over the lists).
    """
    full = lists[~lists['partial']].sort_values(['community', 'effective_date', 'as_of'])
    g = full.groupby(['community', 'effective_date'])
    history = g.agg(cls=('cls', 'last'), first_list=('list_date', 'first'), last_list=('list_date', 'last'),
                    n_classes=('cls', 'nunique')).reset_index().rename(columns={'effective_date': 'from_date'})
    entry = full.groupby('community').agg(entry_date=('entry_date', 'min'),
                                          n_entry_dates=('entry_date', 'nunique')).reset_index()
    if status_book is not None:
        last = full['as_of'].max()
        sb = status_book[status_book['cls'].notna() & (status_book['effective_date'] > last)]
        add = pd.DataFrame({'community': sb['community'], 'from_date': sb['effective_date'], 'cls': sb['cls'],
                            'first_list': 'status_book', 'last_list': 'status_book', 'n_classes': 1})
        history = pd.concat([history, add], ignore_index=True)
        new = sb[~sb['community'].isin(entry['community'])]
        entry = pd.concat([entry, pd.DataFrame({'community': new['community'], 'entry_date': new['entry_date'],
                                                'n_entry_dates': 1})], ignore_index=True)
    for c, d, k in set_class:
        d = pd.Timestamp(d)
        add = pd.DataFrame({'community': [c], 'from_date': [d], 'cls': [k], 'first_list': ['fix'],
                            'last_list': ['fix'], 'n_classes': [1]})
        history = _override(history, c, d, add)
    for c, other, d in follow:
        d = pd.Timestamp(d)
        h = history[history['community'] == other].sort_values('from_date')
        before, after = h[h['from_date'] <= d], h[h['from_date'] > d]
        if before.empty:
            raise ValueError(f'{other} has no class on {d.date()}')
        add = pd.concat([before.tail(1).assign(from_date=d), after]).assign(
            community=c, first_list=f'follow {other}', last_list=f'follow {other}', n_classes=1)
        history = _override(history, c, d, add)
    history['cls'] = history['cls'].astype(int)
    history = history.sort_values(['community', 'from_date']).reset_index(drop=True)
    return history, entry.sort_values('community').reset_index(drop=True)


def class_at(history, entry, community, dates, list_dates):
    """Class and flag of each (community, date) pair, by the rules in the module docstring.

    ``community``, ``dates``: array-likes of equal length (6-character strings, datetimes). ``list_dates``: sorted
    full-list dates (``full_list_dates``), for the ``gap`` flag. Returns a DataFrame (same order as the input) with
    ``cls`` (float, NaN = unknown) and ``flag`` ('' | 'unknown' | 'gap').
    """
    q = pd.DataFrame({'community': pd.Series(community, dtype=str).values,
                      'date': pd.to_datetime(pd.Series(dates)).values.astype('datetime64[ns]')})
    q['_i'] = np.arange(len(q))
    q = q.merge(entry[['community', 'entry_date']], on='community', how='left')
    h = history[['community', 'from_date', 'cls']].rename(columns={'from_date': 'date', 'cls': '_cls'})
    h['date'] = h['date'].values.astype('datetime64[ns]')       # merge_asof needs one resolution on both sides
    q['entry_date'] = q['entry_date'].values.astype('datetime64[ns]')
    s = q.dropna(subset=['date']).sort_values('date')
    s = pd.merge_asof(s, h.sort_values('date'), on='date', by='community', direction='backward')
    q = q.merge(s[['_i', '_cls']], on='_i', how='left').sort_values('_i').reset_index(drop=True)

    in_crs = q['entry_date'].notna() & (q['date'] >= q['entry_date'])
    cls = np.where(in_crs, q['_cls'], NOT_IN_CRS).astype(float)          # rules 2 and 5; rule 1 inside CRS
    unknown = in_crs & q['_cls'].isna()                                    # rule 3
    cls[unknown.values] = np.nan

    ld = np.asarray(list_dates, dtype='datetime64[ns]')
    d = q['date'].values.astype('datetime64[ns]')
    k = np.searchsorted(ld, d, side='right')                              # ld[k-1] <= d < ld[k]
    inside = (k > 0) & (k < len(ld))
    inside[inside] &= d[inside] != ld[k[inside] - 1]                       # a list date itself is not inside a gap
    span = np.full(len(d), np.timedelta64(0, 'D'))
    span[inside] = ld[k[inside]] - ld[k[inside] - 1]
    gap = in_crs.values & inside & (span > np.timedelta64(GAP_DAYS, 'D'))  # rule 4
    flag = np.where(unknown, 'unknown', np.where(gap, 'gap', ''))
    return pd.DataFrame({'cls': cls, 'flag': flag})
