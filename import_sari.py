#!/usr/bin/env python3
"""Validate the resident-based SARI cube and build chart data feeds."""
import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

SOURCE = 'https://opendata-files.sozialversicherung.at/sari/SARI_Wohnregion_Patient_v202602.csv?q=now'
SOURCE_CREDIT = 'Statistische Daten des Dachverbandes der Sozialversicherungsträger'
REGIONS = {'BGL', 'KTN', 'NÖ', 'OÖ', 'SBG', 'ST', 'T', 'V', 'W'}
AGE_ORDER = ['0 - 4', '5 - 14', '15 - 29', '30 - 44', '45 - 59', '60 - 69', '70 - 79', '80+']
AGES = set(AGE_ORDER)
METRICS = ['AUFNAHMEN', 'COVID', 'INFLUENZA', 'RSV', 'PNEUMOKOKKEN', 'SONSTIGE']
DIMS = ['JAHR', 'KW', 'WOHNORT', 'GESCHLECHT', 'ALTERSGRUPPE', 'STATION']
RATE_BASE = 100_000
MAX_BYTES = 20_000_000


def parse_source(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Source too large')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';')
    if not set(DIMS + METRICS + ['BEV_ZAHL']).issubset(reader.fieldnames or []):
        raise ValueError('Changed SARI schema: diagnoses and population are required')
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('Duplicate column names')
    records, seen, populations = [], set(), {}
    week_counts = collections.Counter()
    for row in reader:
        year, week = int(row['JAHR']), int(row['KW'])
        dt.date.fromisocalendar(year, week, 4)
        region, sex, age, station = (row[k] for k in DIMS[2:])
        if (region not in REGIONS or sex not in {'M', 'W'}
                or age not in AGES or station not in {'N', 'I'}):
            raise ValueError('Changed source categories')
        key = (year, week, region, sex, age, station)
        if key in seen:
            raise ValueError('Duplicate source row')
        seen.add(key)
        values = tuple(int(row[k]) for k in METRICS)
        if any(value < 0 for value in values):
            raise ValueError('Negative admissions')
        if any(value > values[0] for value in values[1:]):
            raise ValueError('A diagnosis exceeds total admissions')
        population = int(row['BEV_ZAHL'])
        if population <= 0:
            raise ValueError('Population must be positive')
        pop_key = key[:-1]
        if pop_key in populations and populations[pop_key] != population:
            raise ValueError('Population differs between normal and intensive care')
        populations[pop_key] = population
        records.append((key, values))
        week_counts[year, week] += 1
    expected = len(REGIONS) * 2 * len(AGES) * 2
    if len(week_counts) < 3 or any(n != expected for n in week_counts.values()):
        raise ValueError('Unexpected row counts: expected 288 cells per week')
    week_keys = sorted(week_counts)
    weeks = []
    for index, (year, week) in enumerate(week_keys):
        date = dt.date.fromisocalendar(year, week, 4)
        if weeks and (date - dt.date.fromisoformat(weeks[-1]['date'])).days != 7:
            raise ValueError('Missing week')
        weeks.append({
            'year': year, 'week': week, 'date': date.isoformat(),
            'season': date.year if date.month >= 10 else date.year - 1,
            'provisional': index >= len(week_keys) - 2,
        })
    return sorted(records), populations, weeks


def metadata(raw, retrieved):
    return {
        'version': 1, 'retrievedAt': retrieved, 'sourceUrl': SOURCE,
        'sourceSha256': hashlib.sha256(raw).hexdigest(), 'sourceCredit': SOURCE_CREDIT,
    }


def legacy_feed(records, weeks, meta):
    totals = collections.Counter()
    for key, values in records:
        totals[key[:2]] += values[0]
    return {**meta, 'metric': 'AUFNAHMEN',
            'weeks': [{**w, 'value': totals[w['year'], w['week']]} for w in weeks]}


def transform(raw, retrieved):
    """Keep the existing title-chart API intact."""
    records, _, weeks = parse_source(raw)
    return legacy_feed(records, weeks, metadata(raw, retrieved))

def aggregate_feed(records, populations, weeks, meta, breakdown):
    """Deduplicate population in each group; never average subgroup rates."""
    groups = {}
    for key, values in records:
        year, week, region, sex, age, station = key
        for selected_station in (station, 'ALL'):
            group = (year, week, region if breakdown == 'region' else 'AT',
                     'ALL', age if breakdown == 'age' else 'ALL', selected_station)
            if group not in groups:
                groups[group] = ([0] * len(METRICS), set())
            totals, population_keys = groups[group]
            for index, value in enumerate(values):
                totals[index] += value
            population_keys.add(key[:-1])
    rows = []
    for key, (totals, pop_keys) in sorted(groups.items()):
        population = sum(populations[p] for p in pop_keys)
        rates = [round(value / population * RATE_BASE, 6) for value in totals]
        rows.append([*key, population, *totals, *rates])
    return {
        **meta, 'rateBase': RATE_BASE, 'weeks': weeks,
        'columns': ['year', 'week', 'region', 'sex', 'age', 'station', 'population']
                   + METRICS + [metric + '_per100k' for metric in METRICS],
        'rows': rows,
    }


def create_bundle(raw, retrieved):
    records, populations, weeks = parse_source(raw)
    meta = metadata(raw, retrieved)
    bundle = {'monitor.json': legacy_feed(records, weeks, meta)}
    for filename, breakdown in [('austria', None), ('ages', 'age'), ('regions', 'region')]:
        bundle['data/' + filename + '.json'] = aggregate_feed(
            records, populations, weeks, meta, breakdown)
    # Full granularity for combined filters. Population has NO station dimension.
    bundle['data/details.json'] = {
        **meta, 'rateBase': RATE_BASE, 'weeks': weeks,
        'admissions': {
            'columns': ['year', 'week', 'region', 'sex', 'age', 'station'] + METRICS,
            'rows': [[*key, *values] for key, values in records],
        },
        'population': {
            'columns': ['year', 'week', 'region', 'sex', 'age', 'population'],
            'rows': [[*key, value] for key, value in sorted(populations.items())],
        },
    }
    bundle['data/index.json'] = {
        **meta, 'rateBase': RATE_BASE, 'weeks': weeks,
        'files': {'austria': 'austria.json', 'ages': 'ages.json',
                  'regions': 'regions.json', 'details': 'details.json'},
        'dimensions': {
            'region': {'AT': 'Österreich', 'BGL': 'Burgenland', 'KTN': 'Kärnten',
                       'NÖ': 'Niederösterreich', 'OÖ': 'Oberösterreich', 'SBG': 'Salzburg',
                       'ST': 'Steiermark', 'T': 'Tirol', 'V': 'Vorarlberg', 'W': 'Wien'},
            'age': AGE_ORDER, 'sex': {'M': 'männlich', 'W': 'weiblich', 'ALL': 'Gesamt'},
            'station': {'N': 'Normalstation', 'I': 'Intensivstation', 'ALL': 'Alle Stationen'},
            'aggregateCode': 'ALL',
        },
        'metrics': {
            'AUFNAHMEN': 'Alle SARI-Aufnahmen', 'COVID': 'COVID-19',
            'INFLUENZA': 'Influenza', 'RSV': 'RSV',
            'PNEUMOKOKKEN': 'Pneumokokken-Pneumonie', 'SONSTIGE': 'Sonstige SARI-Diagnosen',
        },
        'methodology': {
            'geography': 'Wohnsitz Österreich; Bundesland nach Wohnort bei Aufnahme',
            'measure': 'Wöchentliche Aufnahmen, keine Bettenbelegung oder Zahl aller Infektionen',
            'rate': 'Aufnahmen / Bevölkerung derselben Woche und Bevölkerungsgruppe * 100000',
            'ratePrecision': 'Sechs Dezimalstellen; Anzeige rundet erst im Diagramm',
            'population': 'BEV_ZAHL einmal je Woche, Region, Geschlecht und Alter; nicht je Station addieren',
            'diagnoses': 'Diagnosegruppen überschneiden sich; Gesamtwert ausschließlich AUFNAHMEN',
            'stations': 'ALL enthält bereits N und I; nicht erneut addieren',
            'provisional': 'Neueste zwei vorhandene Wochen unvollständig; ältere Werte ebenfalls revidierbar',
            'season': 'Oktober–September, Zuordnung nach ISO-Wochen-Donnerstag; Startjahr als Zahl',
            'retrievedAt': 'Erfolgreicher Abrufzeitpunkt, nicht Veröffentlichungsdatum der Quelle',
        },
    }
    return bundle


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.sari-',
                                         suffix='.tmp', encoding='utf-8', delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def write_bundle(bundle, output, data_dir):
    """Serialize every feed before replacing data. Pages deploys only on success."""
    output, data_dir = Path(output), Path(data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.sari-bundle-', dir=output.parent) as directory:
        staging = Path(directory)
        for name, data in bundle.items():
            atomic_json(staging / name, data)
        data_dir.mkdir(parents=True, exist_ok=True)
        for name in bundle:
            if name not in {'monitor.json', 'data/index.json'}:
                os.replace(staging / name, data_dir / Path(name).name)
        os.replace(staging / 'monitor.json', output)
        os.replace(staging / 'data/index.json', data_dir / 'index.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input')
    parser.add_argument('--output', default=str(Path(__file__).with_name('monitor.json')))
    parser.add_argument('--data-dir', help='Default: data/ next to the output JSON')
    parser.add_argument('--archive-dir')
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    output = Path(args.output)
    data_dir = Path(args.data_dir) if args.data_dir else output.parent / 'data'
    try:
        if args.input:
            raw = Path(args.input).read_bytes()
            retrieved = dt.datetime.fromtimestamp(Path(args.input).stat().st_mtime,
                                                 dt.timezone.utc).isoformat()
        else:
            request = urllib.request.Request(SOURCE, headers={'User-Agent': 'KURIER-SARI-Monitor/2.0'})
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(MAX_BYTES + 1)
            retrieved = now
        bundle = create_bundle(raw, retrieved)
        data = bundle['monitor.json']
        if output.exists():
            previous = json.loads(output.read_text())
            previous_dates = {week['date'] for week in previous['weeks']}
            if not previous_dates.issubset({week['date'] for week in data['weeks']}):
                raise ValueError('Source series regressed or lost historical weeks')
        if args.archive_dir:
            archive = Path(args.archive_dir)
            archive.mkdir(parents=True, exist_ok=True)
            archived = archive / (data['sourceSha256'] + '.csv.gz')
            if not archived.exists():
                archived.write_bytes(gzip.compress(raw, mtime=0))
        write_bundle(bundle, output, data_dir)
        atomic_json(output.with_name('status.json'), {
            'ok': True, 'attemptedAt': now, 'retrievedAt': retrieved,
            'sourceSha256': data['sourceSha256'], 'feeds': len(bundle),
            'latestWeek': data['weeks'][-1]['week'], 'latestYear': data['weeks'][-1]['year'],
        })
        print('OK', now, 'weeks', len(data['weeks']), 'feeds', len(bundle),
              'latest', data['weeks'][-1]['year'], data['weeks'][-1]['week'])
    except Exception as error:
        atomic_json(output.with_name('status.json'), {
            'ok': False, 'attemptedAt': now, 'error': str(error),
        })
        print('FAILED:', str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
