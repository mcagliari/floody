''' Read latitude bands of LOCA2 monthly files over HTTP byte ranges.

LOCA2 files on the authors' server (https://cirrus.ucsd.edu/~pierce/LOCA2/) are classic
netCDF (CDF-1/CDF-2): each record (= one month) stores the whole lat x lon grid row by row.
Full-width latitude bands are therefore contiguous within a record, and a band of one
record is a single byte range. This module

- parses the classic-netCDF header (no netCDF library needed, and only the header is
  downloaded);
- turns lat/lon boxes into merged full-width bands and their byte ranges;
- fetches many ranges per multi-range request, with guards against the server answering
  with the whole file (Apache does that when a request exceeds its range limit);
- cuts the boxes out of the bands;
- does the same on a downloaded local file (`LocalReader`, same interface), with a resumable
  whole-file download (`download_file`) and the output writer (`save_boxes`).

Nothing here is specific to a city or a model: callers pass boxes and a file URL.
'''
import hashlib
import os
import struct
import time

import numpy as np
import requests

# netCDF classic types: code -> (numpy big-endian dtype, size in bytes)
_NC_TYPES = {1: ('>i1', 1), 2: ('S1', 1), 3: ('>i2', 2), 4: ('>i4', 4), 5: ('>f4', 4), 6: ('>f8', 8)}
_NC_DIMENSION, _NC_VARIABLE, _NC_ATTRIBUTE = 0x0A, 0x0B, 0x0C


class _NeedMore(Exception):
    ''' header parsing ran past the end of the buffer '''


class _Cursor(object):
    def __init__(self, buf):
        self.buf, self.pos = buf, 0

    def take(self, n):
        if self.pos + n > len(self.buf):
            raise _NeedMore
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def int32(self):
        return struct.unpack('>i', self.take(4))[0]

    def uint32(self):
        return struct.unpack('>I', self.take(4))[0]

    def int64(self):
        return struct.unpack('>q', self.take(8))[0]

    def name(self):
        n = self.int32()
        s = self.take(n).decode('utf-8')
        self.take((4 - n % 4) % 4)
        return s

    def values(self, nc_type, n):
        dtype, size = _NC_TYPES[nc_type]
        raw = self.take(n * size)
        self.take((4 - (n * size) % 4) % 4)
        if nc_type == 2:
            return raw.decode('utf-8', errors='replace').rstrip('\x00')
        return np.frombuffer(raw, dtype=dtype)


def _attributes(cur):
    tag, n = cur.int32(), cur.int32()
    if tag == 0 and n == 0:
        return {}
    if tag != _NC_ATTRIBUTE:
        raise ValueError('bad attribute list tag %r' % tag)
    atts = {}
    for _ in range(n):
        name = cur.name()
        nc_type, nelems = cur.int32(), cur.int32()
        atts[name] = cur.values(nc_type, nelems)
    return atts


def parse_header(buf):
    ''' Parse a classic-netCDF (CDF-1 or CDF-2) header from the first bytes of a file.

    Returns a dict with `version`, `numrecs`, `dims` (name -> length, 0 = record dimension),
    `attrs` (global), `vars` (name -> dict: `dims`, `attrs`, `dtype`, `vsize`, `begin`,
    `is_record`, `shape` without the record dimension), `recsize` and `header_size`.
    Raises `_NeedMore` if `buf` is too short.
    '''
    cur = _Cursor(buf)
    magic = cur.take(4)
    if magic[:3] != b'CDF' or magic[3] not in (1, 2):
        raise ValueError('not a classic netCDF (CDF-1/CDF-2) file: %r' % magic)
    version = magic[3]
    numrecs = cur.uint32()

    tag, n = cur.int32(), cur.int32()
    dims = []
    if not (tag == 0 and n == 0):
        if tag != _NC_DIMENSION:
            raise ValueError('bad dimension list tag %r' % tag)
        for _ in range(n):
            dims.append((cur.name(), cur.int32()))
    gatts = _attributes(cur)

    tag, n = cur.int32(), cur.int32()
    variables = {}
    if not (tag == 0 and n == 0):
        if tag != _NC_VARIABLE:
            raise ValueError('bad variable list tag %r' % tag)
        for _ in range(n):
            name = cur.name()
            ndims = cur.int32()
            dimids = [cur.int32() for _ in range(ndims)]
            atts = _attributes(cur)
            nc_type, vsize = cur.int32(), cur.int32()
            begin = cur.int64() if version == 2 else cur.int32()
            vdims = [dims[i][0] for i in dimids]
            is_record = len(dimids) > 0 and dims[dimids[0]][1] == 0
            shape = tuple(dims[i][1] for i in (dimids[1:] if is_record else dimids))
            variables[name] = dict(dims=vdims, attrs=atts, dtype=_NC_TYPES[nc_type][0],
                                   itemsize=_NC_TYPES[nc_type][1], vsize=vsize, begin=begin,
                                   is_record=is_record, shape=shape)

    rec = [v for v in variables.values() if v['is_record']]
    if len(rec) == 1:   # a single record variable is not padded (netCDF classic spec)
        recsize = int(np.prod(rec[0]['shape'])) * rec[0]['itemsize']
    else:
        recsize = sum(v['vsize'] for v in rec)
    return dict(version=version, numrecs=numrecs, dims=dict(dims), attrs=gatts, vars=variables,
                recsize=recsize, header_size=cur.pos)


class _Reader(object):
    ''' shared by the readers: subclasses define `fetch(ranges) -> {(start, end): bytes}` '''

    def header(self, first=1 << 20):
        ''' read and parse the header, growing the prefix until it parses (a reader with a
        known `size` never reads past the end of the file) '''
        size = getattr(self, 'size', None)
        n = first
        while True:
            m = n if size is None else min(n, size)
            buf = self.fetch([(0, m - 1)])[(0, m - 1)]
            try:
                return parse_header(buf)
            except _NeedMore:
                if m == size:
                    raise ValueError('header runs past the end of the file')
                n *= 2

    def static_variable(self, hdr, name):
        ''' a non-record variable (e.g. lat, lon) '''
        v = hdr['vars'][name]
        if v['is_record']:
            raise ValueError('%s is a record variable' % name)
        nbytes = int(np.prod(v['shape'])) * v['itemsize']
        raw = self.fetch([(v['begin'], v['begin'] + nbytes - 1)])[(v['begin'], v['begin'] + nbytes - 1)]
        return np.frombuffer(raw, dtype=v['dtype']).reshape(v['shape'])


class LocalReader(_Reader):
    ''' Same interface as `RangeReader`, on a local file. '''

    def __init__(self, path):
        self.path, self.size = path, os.path.getsize(path)
        self.n_requests, self.n_bytes = 0, 0

    def fetch(self, ranges):
        ''' {(start, end): bytes} for inclusive ranges; raises if the file is too short '''
        out = {}
        with open(self.path, 'rb') as f:
            for a, b in ranges:
                f.seek(a)
                data = f.read(b - a + 1)
                if len(data) != b - a + 1:
                    raise RuntimeError('range %d-%d beyond the end of %s' % (a, b, self.path))
                out[(a, b)] = data
                self.n_bytes += len(data)
        self.n_requests += 1
        return out


class RangeReader(_Reader):
    ''' Multi-range HTTP reader for one file, with guards and a pause between requests.

    Parameters
    ----------
    url : str
    verify : str or bool
        passed to `requests` (a CA-bundle path when the server's certificate chain is
        incomplete; never False).
    max_ranges : int
        ranges per request (Apache's default `MaxRanges` is 200; above it Apache sends the
        whole file, which the guard below refuses).
    pause : float
        seconds to wait after each request.
    '''

    def __init__(self, url, verify=True, max_ranges=100, pause=0.5, session=None, timeout=120):
        if verify is False:
            raise ValueError('certificate verification must stay on')
        self.url, self.verify, self.max_ranges, self.pause = url, verify, max_ranges, pause
        self.session = session or requests.Session()
        self.timeout = timeout
        self.n_requests, self.n_bytes = 0, 0

    def _request(self, ranges):
        ''' one request for a list of (start, end) inclusive ranges -> {(start, end): bytes} '''
        want = sum(b - a + 1 for a, b in ranges)
        limit = want + 400 * len(ranges) + 2048          # payload + multipart headers
        hdr = {'Range': 'bytes=' + ','.join('%d-%d' % r for r in ranges)}
        resp = self.session.get(self.url, headers=hdr, stream=True, verify=self.verify, timeout=self.timeout)
        try:
            if resp.status_code != 206:
                raise RuntimeError('server answered %d instead of 206 (partial content); aborted '
                                   'without reading the body' % resp.status_code)
            body, got = [], 0
            for chunk in resp.iter_content(1 << 16):
                got += len(chunk)
                if got > limit:
                    raise RuntimeError('response larger than requested (%d > %d bytes); aborted' % (got, limit))
                body.append(chunk)
            body = b''.join(body)
            ctype = resp.headers.get('Content-Type', '')
        finally:
            resp.close()
        self.n_requests += 1
        self.n_bytes += len(body)
        time.sleep(self.pause)

        parts = []                                          # (start, end, bytes)
        if ctype.startswith('multipart/byteranges'):
            boundary = ('--' + ctype.split('boundary=')[1].strip().strip('"')).encode()
            pos = 0
            while True:
                i = body.find(boundary, pos)
                if i < 0 or body[i + len(boundary):i + len(boundary) + 2] == b'--':
                    break
                j = body.find(b'\r\n\r\n', i)
                head = body[i:j].decode('latin-1')
                cr = [l for l in head.split('\r\n') if l.lower().startswith('content-range:')][0]
                a, b = cr.split('bytes')[1].strip().split('/')[0].split('-')
                a, b = int(a), int(b)
                parts.append((a, b, body[j + 4:j + 4 + b - a + 1]))
                pos = j + 4 + b - a + 1
        else:
            cr = resp.headers['Content-Range']
            a, b = cr.split('bytes')[1].strip().split('/')[0].split('-')
            parts.append((int(a), int(b), body))

        out = {}
        for a, b in ranges:                                 # robust to the server merging ranges
            for pa, pb, data in parts:
                if pa <= a and b <= pb:
                    out[(a, b)] = data[a - pa:b - pa + 1]
                    break
            else:
                raise RuntimeError('range %d-%d missing from the response' % (a, b))
            if len(out[(a, b)]) != b - a + 1:
                raise RuntimeError('range %d-%d truncated' % (a, b))
        return out

    def fetch(self, ranges):
        ''' all ranges, `max_ranges` per request -> {(start, end): bytes} '''
        out = {}
        for k in range(0, len(ranges), self.max_ranges):
            out.update(self._request(ranges[k:k + self.max_ranges]))
        return out


def box_indices(lat, lon, box):
    ''' (row slice, column slice) of the grid cells whose centres lie in
    box = (lat_min, lat_max, lon_min, lon_max) in degrees east (-180..180 or 0..360) '''
    lat_min, lat_max, lon_min, lon_max = box
    if np.nanmax(lon) > 180:                                # grid in 0..360
        lon_min, lon_max = lon_min % 360, lon_max % 360
    rows = np.where((lat >= lat_min) & (lat <= lat_max))[0]
    cols = np.where((lon >= lon_min) & (lon <= lon_max))[0]
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError('box %s has no grid cell' % (box,))
    if np.any(np.diff(rows) != 1) or np.any(np.diff(cols) != 1):
        raise ValueError('box %s is not contiguous on the grid' % (box,))
    return slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)


def merge_bands(row_slices):
    ''' merge overlapping or adjacent row slices into bands -> sorted list of slices '''
    s = sorted((r.start, r.stop) for r in row_slices)
    bands = [list(s[0])]
    for a, b in s[1:]:
        if a <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], b)
        else:
            bands.append([a, b])
    return [slice(a, b) for a, b in bands]


def extract_boxes(reader, hdr, var, boxes, lat_name='lat', lon_name='lon', time_name='time', records=None):
    ''' Cut lat/lon boxes out of record variable `var` (dims: record, lat, lon).

    boxes : dict name -> (lat_min, lat_max, lon_min, lon_max)
    records : iterable of record indices (default: all)
    Returns dict name -> dict(data=(nrec, nlat, nlon) array in the file's dtype, as stored
    (no scaling, no masking), lat, lon, rows, cols) and, under key '_time', the time values.
    '''
    v = hdr['vars'][var]
    if not v['is_record'] or v['dims'][1:] != [lat_name, lon_name]:
        raise ValueError('%s must have dims (record, %s, %s); has %s' % (var, lat_name, lon_name, v['dims']))
    lat, lon = reader.static_variable(hdr, lat_name), reader.static_variable(hdr, lon_name)
    nlat, nlon = v['shape']
    item = v['itemsize']
    records = np.arange(hdr['numrecs']) if records is None else np.asarray(records)

    idx = {k: box_indices(lat, lon, b) for k, b in boxes.items()}
    bands = merge_bands([r for r, _ in idx.values()])
    tv = hdr['vars'][time_name]

    ranges, keys = [], []
    for rec in records:
        base = rec * hdr['recsize']
        for bd in bands:
            a = v['begin'] + base + bd.start * nlon * item
            ranges.append((a, a + (bd.stop - bd.start) * nlon * item - 1))
            keys.append(('band', rec, bd.start))
        a = tv['begin'] + base
        ranges.append((a, a + tv['itemsize'] - 1))
        keys.append(('time', rec, None))
    got = reader.fetch(ranges)

    band_data = {}
    times = np.empty(len(records), dtype=tv['dtype'])
    rpos = {rec: i for i, rec in enumerate(records)}
    for key, rg in zip(keys, ranges):
        if key[0] == 'time':
            times[rpos[key[1]]] = np.frombuffer(got[rg], dtype=tv['dtype'])[0]
        else:
            band_data[(key[1], key[2])] = np.frombuffer(got[rg], dtype=v['dtype']).reshape(-1, nlon)

    out = {'_time': times}
    for k, (rs, cs) in idx.items():
        bd = [b for b in bands if b.start <= rs.start and rs.stop <= b.stop][0]
        arr = np.stack([band_data[(rec, bd.start)][rs.start - bd.start:rs.stop - bd.start, cs] for rec in records])
        out[k] = dict(data=arr, lat=lat[rs], lon=lon[cs], rows=rs, cols=cs)
    return out


def grid_variable(hdr, lat_name='lat', lon_name='lon'):
    ''' name of the single record variable with dims (record, lat, lon); raises if not exactly one '''
    names = [n for n, v in hdr['vars'].items() if v['is_record'] and v['dims'][1:] == [lat_name, lon_name]]
    if len(names) != 1:
        raise ValueError('expected one (record, %s, %s) variable, found %s' % (lat_name, lon_name, names))
    return names[0]


def md5_file(path, chunk=1 << 24):
    m = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            m.update(b)
    return m.hexdigest()


def download_file(url, path, verify=True, session=None, tries=5, wait=10, timeout=300, chunk=1 << 22):
    ''' Download `url` to `path` over one connection, resuming after a dropped connection
    (byte range from the bytes already on disk). Returns (size, md5). Raises if the final size
    differs from the server's Content-Length or the server does not honour the resume.
    '''
    if verify is False:
        raise ValueError('certificate verification must stay on')
    s = session or requests.Session()
    head = s.head(url, verify=verify, timeout=60, allow_redirects=True)
    head.raise_for_status()
    total = int(head.headers['Content-Length'])
    for _ in range(tries):
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if have > total:
            os.remove(path)
            have = 0
        if have == total:
            break
        hdr = {'Range': 'bytes=%d-' % have} if have else {}
        try:
            with s.get(url, headers=hdr, stream=True, verify=verify, timeout=timeout) as r:
                if r.status_code != (206 if have else 200):
                    raise RuntimeError('server answered %d (expected %d)' % (r.status_code, 206 if have else 200))
                with open(path, 'ab' if have else 'wb') as f:
                    for b in r.iter_content(chunk):
                        f.write(b)
        except requests.exceptions.RequestException:
            time.sleep(wait)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size != total:
        raise RuntimeError('%s: %d of %d bytes after %d tries' % (url, size, total, tries))
    return size, md5_file(path)


def save_boxes(path, out, boxes, hdr, var, source_url, method):
    ''' Write the output of `extract_boxes` to netCDF4 (h5netcdf), one variable per box
    (`<var>_<box>`, dims time, lat_<box>, lon_<box>), values as stored in the source file.
    Same layout as the pilot (workspace notebook 09). Needs xarray + h5netcdf.
    '''
    import datetime
    import xarray as xr
    tv = hdr['vars'].get('time', {'attrs': {}})
    miss = np.asarray(hdr['vars'][var]['attrs'].get('missing_value', [np.nan]))
    ds = xr.Dataset(attrs=dict(source_url=source_url, LOCA2_version=str(hdr['attrs'].get('LOCA2_version', '')),
                               variable=var, units=str(hdr['vars'][var]['attrs'].get('units', '')),
                               extracted=datetime.datetime.now().isoformat(timespec='seconds'), method=method))
    ds['time'] = ('time', out['_time'].astype('f8'), {'units': str(tv['attrs'].get('units', '')),
                                                    'calendar': str(tv['attrs'].get('calendar', ''))})
    for k in boxes:
        e = out[k]
        ds['%s_%s' % (var, k)] = (('time', 'lat_%s' % k, 'lon_%s' % k), e['data'].astype(np.float32),
                                  {'box': list(boxes[k]), 'missing_value': float(miss.ravel()[0])})
        ds['lat_%s' % k] = ('lat_%s' % k, e['lat'].astype('f8'))
        ds['lon_%s' % k] = ('lon_%s' % k, e['lon'].astype('f8'))
    ds.to_netcdf(path, engine='h5netcdf')
    return path
