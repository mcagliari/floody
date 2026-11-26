import numpy as np
import pandas as pd

from floody import crs


def _lists():
    rows = [  # list_date, as_of, community, entry, effective, cls, partial
        ('2010-05', '2010-05-01', '000001', '2005-10-01', '2008-10-01', 8, False),
        ('2010-10', '2010-10-01', '000001', '2005-10-01', '2010-10-01', 7, False),
        ('2012-10', '2012-10-01', '000001', '2005-10-01', '2010-10-01', 7, False),   # 2-year gap before this list
        ('2012-10', '2012-10-01', '000002', '2011-05-01', '2011-05-01', 9, False),
        ('2013-05', '2013-05-01', '000002', None, None, 9, True),                    # partial: not used
    ]
    t = pd.DataFrame(rows, columns=['list_date', 'as_of', 'community', 'entry_date', 'effective_date', 'cls', 'partial'])
    for c in ['as_of', 'entry_date', 'effective_date']:
        t[c] = pd.to_datetime(t[c])
    return t


def test_class_at_rules():
    lists = _lists()
    sb = pd.DataFrame({'community': ['000001', '000003'], 'cls': [6.0, 9.0],
                       'entry_date': pd.to_datetime(['2005-10-01', '2013-05-01']),
                       'effective_date': pd.to_datetime(['2013-05-01', '2013-05-01'])})
    hist, entry = crs.crs_history(lists, sb)
    assert hist['community'].tolist() == ['000001'] * 3 + ['000002', '000003']
    assert hist['cls'].tolist() == [8, 7, 6, 9, 9]
    ld = crs.full_list_dates(lists)
    q = [('000001', '2004-01-01', 10, ''),        # rule 2: before entry
         ('000001', '2007-01-01', np.nan, 'unknown'),   # rule 3
         ('000001', '2009-01-01', 8, ''),
         ('000001', '2011-06-01', 7, 'gap'),       # rule 4: 2010-10 -> 2012-10
         ('000001', '2012-10-01', 7, ''),          # list date itself
         ('000001', '2014-01-01', 6, ''),          # rule 7: Status Book after the last list
         ('000002', '2011-06-01', 9, 'gap'),
         ('000003', '2014-01-01', 9, ''),          # rule 7, community in no list
         ('999999', '2014-01-01', 10, '')]         # rule 5
    out = crs.class_at(hist, entry, [r[0] for r in q], [r[1] for r in q], ld)
    np.testing.assert_array_equal(out['cls'].values, np.array([r[2] for r in q], dtype=float))
    assert out['flag'].tolist() == [r[3] for r in q]


def test_fixes():
    lists = _lists()
    hist, entry = crs.crs_history(lists, set_class=[('000002', '2012-05-01', 10)],
                                  follow=[('000001', '000002', '2011-06-01')])
    ld = crs.full_list_dates(lists)
    out = crs.class_at(hist, entry, ['000001', '000001', '000002', '000002'],
                       ['2010-12-01', '2011-07-01', '2011-07-01', '2013-01-01'], ld)
    assert out['cls'].tolist() == [7.0, 9.0, 9.0, 10.0]      # 000001 follows 000002 from 2011-06; 000002 -> 10
    assert hist.loc[hist['community'] == '000001', 'from_date'].max() == pd.Timestamp('2012-05-01')
