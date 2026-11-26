from floody.location import STATE_FIPS


def test_state_fips():
    assert len(STATE_FIPS) == 56 and len(set(STATE_FIPS.values())) == 56
    assert all(len(v) == 2 and v.isdigit() for v in STATE_FIPS.values())
    assert (STATE_FIPS['AL'], STATE_FIPS['DC'], STATE_FIPS['TX'], STATE_FIPS['WY'], STATE_FIPS['PR']) == \
        ('01', '11', '48', '56', '72')
