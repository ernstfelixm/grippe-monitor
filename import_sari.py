#!/usr/bin/env python3
"""Fetch and validate all SARI weeks; publish JSON atomically. Python 3.9+."""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

SOURCE='https://opendata-files.sozialversicherung.at/sari/SARI_Wohnregion_Patient_v202602.csv?q=now'
REGIONS={'BGL','KTN','NÖ','OÖ','SBG','ST','T','V','W'}
AGES={'0 - 4','5 - 14','15 - 29','30 - 44','45 - 59','60 - 69','70 - 79','80+'}

def transform(raw, retrieved):
    if len(raw)>20_000_000:raise ValueError('Source too large')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';')
    dims=['JAHR','KW','WOHNORT','GESCHLECHT','ALTERSGRUPPE','STATION']
    if not set(dims+['AUFNAHMEN']).issubset(reader.fieldnames or []):raise ValueError('Changed SARI schema')
    totals=collections.Counter();counts=collections.Counter();seen=set()
    for r in reader:
        key=tuple(r[k] for k in dims)
        if key in seen:raise ValueError('Duplicate source row')
        seen.add(key)
        if r['WOHNORT'] not in REGIONS or r['GESCHLECHT'] not in {'M','W'} or r['ALTERSGRUPPE'] not in AGES or r['STATION'] not in {'N','I'}:raise ValueError('Changed source categories')
        y,w=int(r['JAHR']),int(r['KW']);dt.date.fromisocalendar(y,w,4)
        value=int(r['AUFNAHMEN'])
        if value<0:raise ValueError('Negative admissions')
        totals[y,w]+=value;counts[y,w]+=1
    if len(totals)<3 or any(v!=288 for v in counts.values()):raise ValueError('Unexpected row counts')
    weeks=[]
    for i,((y,w),value) in enumerate(sorted(totals.items())):
        date=dt.date.fromisocalendar(y,w,4)
        if weeks and (date-dt.date.fromisoformat(weeks[-1]['date'])).days!=7:raise ValueError('Missing week')
        weeks.append({'year':y,'week':w,'date':date.isoformat(),'season':date.year if date.month>=10 else date.year-1,'value':value,'provisional':i>=len(totals)-2})
    return {'version':1,'metric':'AUFNAHMEN','retrievedAt':retrieved,'sourceUrl':SOURCE,'sourceSha256':hashlib.sha256(raw).hexdigest(),'weeks':weeks}

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.sari-',suffix='.tmp',encoding='utf-8',delete=False) as f:
            name=f.name;json.dump(data,f,ensure_ascii=False,separators=(',',':'));f.flush();os.fsync(f.fileno())
        os.chmod(name,0o644);os.replace(name,path)
    finally:
        if name and Path(name).exists():Path(name).unlink()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input');ap.add_argument('--output',default=str(Path(__file__).with_name('monitor.json')));ap.add_argument('--archive-dir');args=ap.parse_args()
    now=dt.datetime.now(dt.timezone.utc).isoformat();output=Path(args.output)
    try:
        if args.input:
            raw=Path(args.input).read_bytes()
            retrieved=dt.datetime.fromtimestamp(Path(args.input).stat().st_mtime,dt.timezone.utc).isoformat()
        else:
            request=urllib.request.Request(SOURCE,headers={'User-Agent':'KURIER-SARI-Monitor/1.0'})
            with urllib.request.urlopen(request,timeout=45) as response:raw=response.read(20_000_001)
            retrieved=now
        data=transform(raw,retrieved)
        if output.exists():
            previous=json.loads(output.read_text())
            if data['weeks'][-1]['date']<previous['weeks'][-1]['date']:raise ValueError('Source series regressed')
        if args.archive_dir:
            archive=Path(args.archive_dir);archive.mkdir(parents=True,exist_ok=True)
            archived=archive/(data['sourceSha256']+'.csv.gz')
            if not archived.exists():archived.write_bytes(gzip.compress(raw,mtime=0))
        atomic_json(output,data)
        atomic_json(output.with_name('status.json'),{'ok':True,'attemptedAt':now,'latestWeek':data['weeks'][-1]['week'],'latestYear':data['weeks'][-1]['year']})
        print('OK',now,'weeks',len(data['weeks']),'latest',data['weeks'][-1]['year'],data['weeks'][-1]['week'])
    except Exception as e:
        atomic_json(output.with_name('status.json'),{'ok':False,'attemptedAt':now,'error':str(e)})
        print('FAILED:',str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
