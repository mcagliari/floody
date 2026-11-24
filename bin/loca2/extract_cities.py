#!/usr/bin/env python
''' Download LOCA2 monthly files one at a time, cut the city boxes, keep only the cut.

Walks the file list in order. Per file: skip if its output exists -> download the whole file
(one connection, resumable) -> size check against the server, md5 -> cut the boxes with the
verified header/band code (`floody.loca2`, LocalReader) -> write `<file>.cities.nc` (written to
a temporary name, then renamed) -> delete the full file -> one line in `extract_log.csv`.
Stops starting new files when less than `--margin` seconds of `--time-limit` remain, so a chain
of identical batch jobs can be resubmitted until every file is done. A job killed mid-download
leaves a partial file that the next job resumes.

Inputs made locally (workspace notebook 14): the file list (`filelist_ssp370.csv`, columns `url`,
`bytes`) and the boxes (`city_boxes.json`: name -> [lat_min, lat_max, lon_min, lon_max]).
'''
import argparse
import csv
import json
import os
import time
import datetime

import requests
from floody import loca2

USER_AGENT = 'floody-loca2-extract/0.1 (research use; python-requests)'


def main():
    t0 = time.time()
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--filelist', required=True)
    p.add_argument('--boxes', required=True)
    p.add_argument('--ca-bundle', required=True, help='CA bundle incl. the server\'s missing intermediate')
    p.add_argument('--work-dir', required=True, help='where full files are downloaded (deleted after the cut)')
    p.add_argument('--out-dir', required=True)
    p.add_argument('--time-limit', type=float, required=True, help='seconds; equal to the job\'s wall time')
    p.add_argument('--margin', type=float, default=900, help='do not start a new file with less than this left (s)')
    p.add_argument('--max-files', type=int, default=None, help='stop after this many new files (tests)')
    a = p.parse_args()

    os.makedirs(a.work_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(a.filelist) as f:
        files = list(csv.DictReader(f))
    with open(a.boxes) as f:
        boxes = {k: tuple(v) for k, v in json.load(f).items()}
    s = requests.Session()
    s.headers['User-Agent'] = USER_AGENT
    log = os.path.join(a.out_dir, 'extract_log.csv')
    fields = ['file', 'url', 'bytes', 'bytes_in_list', 'md5_full_file', 'months', 'LOCA2_version', 'seconds', 'finished']

    n_new = 0
    for row in files:
        name = row['url'].rsplit('/', 1)[1]
        out = os.path.join(a.out_dir, name[:-len('.nc')] + '.cities.nc')
        if os.path.exists(out):
            continue
        if time.time() - t0 > a.time_limit - a.margin:
            print('time budget reached; stopping before', name, flush=True)
            break
        if a.max_files is not None and n_new >= a.max_files:
            break
        t1 = time.time()
        full = os.path.join(a.work_dir, name)
        size, md5 = loca2.download_file(row['url'], full, verify=a.ca_bundle, session=s)
        if size != int(row['bytes']):
            print('WARNING: %s has %d bytes on the server, %s in the file list (file changed?)' % (name, size, row['bytes']), flush=True)
        rd = loca2.LocalReader(full)
        hdr = rd.header()
        var = loca2.grid_variable(hdr)
        ext = loca2.extract_boxes(rd, hdr, var, boxes)
        tmp = out + '.tmp'
        loca2.save_boxes(tmp, ext, boxes, hdr, var, source_url=row['url'],
                         method='floody.loca2.extract_boxes on the downloaded file (LocalReader, full-width bands)')
        os.replace(tmp, out)
        os.remove(full)
        new_log = not os.path.exists(log)
        with open(log, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if new_log:
                w.writeheader()
            w.writerow(dict(file=name, url=row['url'], bytes=size, bytes_in_list=row['bytes'], md5_full_file=md5,
                            months=hdr['numrecs'], LOCA2_version=str(hdr['attrs'].get('LOCA2_version', '')),
                            seconds=round(time.time() - t1, 1), finished=datetime.datetime.now().isoformat(timespec='seconds')))
        n_new += 1
        print('%s: %.2f GB, %d months, %.0f s' % (name, size / 1e9, hdr['numrecs'], time.time() - t1), flush=True)

    left = sum(not os.path.exists(os.path.join(a.out_dir, r['url'].rsplit('/', 1)[1][:-3] + '.cities.nc')) for r in files)
    print('this job: %d new files; files left: %d of %d' % (n_new, left, len(files)), flush=True)


if __name__ == '__main__':
    main()
