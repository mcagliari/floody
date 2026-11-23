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
- cuts the boxes out of the bands.

Nothing here is specific to a city or a model: callers pass boxes and a file URL.
'''
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


class RangeReader(object):
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

    def header(self, first=1 << 20):
        ''' download and parse the header, growing the prefix until it parses '''
        n = first
        while True:
            buf = self.fetch([(0, n - 1)])[(0, n - 1)]
            try:
                return parse_header(buf)
            except _NeedMore:
                n *= 2

    def static_variable(self, hdr, name):
        ''' a non-record variable (e.g. lat, lon) '''
        v = hdr['vars'][name]
        if v['is_record']:
            raise ValueError('%s is a record variable' % name)
        nbytes = int(np.prod(v['shape'])) * v['itemsize']
        raw = self.fetch([(v['begin'], v['begin'] + nbytes - 1)])[(v['begin'], v['begin'] + nbytes - 1)]
        return np.frombuffer(raw, dtype=v['dtype']).reshape(v['shape'])


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
