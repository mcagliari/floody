''' floody.loca2 on a small synthetic classic-netCDF file (no network). '''
import numpy as np
from scipy.io import netcdf_file

from floody import loca2


def _write(path, ntime=5, nlat=12, nlon=20):
    rng = np.random.default_rng(0)
    data = rng.random((ntime, nlat, nlon)).astype('>f4')
    with netcdf_file(path, 'w', version=1) as f:
        f.createDimension('time', None)
        f.createDimension('lat', nlat)
        f.createDimension('lon', nlon)
        f.createVariable('lat', 'f4', ('lat',))[:] = np.linspace(25, 36, nlat)
        f.createVariable('lon', 'f4', ('lon',))[:] = np.linspace(260, 279, nlon)
        t = f.createVariable('time', 'f8', ('time',))
        t[:] = np.arange(ntime) + 0.5
        t.units, t.calendar = 'days since 1950-01-01', 'standard'
        v = f.createVariable('pr', 'f4', ('time', 'lat', 'lon'))
        v[:] = data
        v.units, v.missing_value = 'kg m-2 s-1', np.float32(1e20)
        f.LOCA2_version = 'v20240915'
    return data


def _bits(a):
    ''' bit patterns in one byte order, so equal values compare equal bit for bit '''
    return np.ascontiguousarray(a, dtype='<f4').view('<u4')


def test_local_reader_extract_boxes(tmp_path):
    path = str(tmp_path / 'x.nc')
    data = _write(path)
    rd = loca2.LocalReader(path)
    hdr = rd.header()
    var = loca2.grid_variable(hdr)
    assert var == 'pr'
    boxes = {'a': (27, 30, -95, -90), 'b': (29, 33, 270, 275), 'c': (35, 36, -100, -99)}
    out = loca2.extract_boxes(rd, hdr, var, boxes)
    lat, lon = np.linspace(25, 36, 12).astype('f4'), np.linspace(260, 279, 20).astype('f4')
    for k, b in boxes.items():
        rs, cs = loca2.box_indices(lat, lon, b)
        assert np.array_equal(_bits(out[k]['data']), _bits(data[:, rs, cs]))
    assert np.array_equal(out['_time'], np.arange(5) + 0.5)


def test_merge_bands():
    assert loca2.merge_bands([slice(5, 8), slice(0, 3), slice(3, 4), slice(7, 10)]) == [slice(0, 4), slice(5, 10)]


def test_save_boxes_roundtrip(tmp_path):
    ''' save_boxes writes what extract_boxes returned, bit for bit, with the source attributes (needs h5py). '''
    import xarray as xr
    path = str(tmp_path / 'x.nc')
    _write(path)
    rd = loca2.LocalReader(path)
    hdr = rd.header()
    boxes = {'a': (27, 30, -95, -90), 'b': (29, 33, 270, 275)}
    out = loca2.extract_boxes(rd, hdr, 'pr', boxes)
    res = loca2.save_boxes(str(tmp_path / 'x.cities.nc'), out, boxes, hdr, 'pr', source_url='file://x.nc', method='test')
    with xr.open_dataset(res, engine='h5netcdf', mask_and_scale=False, decode_times=False) as ds:
        for k in boxes:
            assert np.array_equal(_bits(ds['pr_%s' % k].values), _bits(out[k]['data']))
            assert np.array_equal(ds['lat_%s' % k].values, out[k]['lat'].astype('f8'))
            assert np.array_equal(ds['lon_%s' % k].values, out[k]['lon'].astype('f8'))
            assert list(ds['pr_%s' % k].attrs['box']) == list(boxes[k])
        assert np.array_equal(ds['time'].values, out['_time'])
        assert (ds['time'].attrs['units'], ds['time'].attrs['calendar']) == ('days since 1950-01-01', 'standard')
        assert {a: ds.attrs[a] for a in ('source_url', 'LOCA2_version', 'variable', 'units')} == \
            dict(source_url='file://x.nc', LOCA2_version='v20240915', variable='pr', units='kg m-2 s-1')
