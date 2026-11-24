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
        f.createVariable('time', 'f8', ('time',))[:] = np.arange(ntime) + 0.5
        f.createVariable('pr', 'f4', ('time', 'lat', 'lon'))[:] = data
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
