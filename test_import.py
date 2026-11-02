import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from build import build
from import_sari import (AGES, AGE_ORDER, METRICS, REGIONS, atomic_json,
                         create_bundle, transform, write_bundle)

RETRIEVED = '2026-11-02T00:00:00Z'
BASE = Path(__file__).parent


def fixture(weeks=((2026, 40), (2026, 41), (2026, 42)), mutate=None):
    text = io.StringIO()
    writer = csv.DictWriter(text, delimiter=';', fieldnames=[
        'JAHR', 'KW', 'WOHNORT', 'GESCHLECHT', 'ALTERSGRUPPE', 'STATION',
        *METRICS, 'BEV_ZAHL'])
    writer.writeheader()
    for year, week in weeks:
        for region_index, region in enumerate(sorted(REGIONS)):
            for sex in ['M', 'W']:
                for age_index, age in enumerate(AGE_ORDER):
                    for station in ['N', 'I']:
                        row = dict(JAHR=year, KW=week, WOHNORT=region, GESCHLECHT=sex,
                                   ALTERSGRUPPE=age, STATION=station,
                                   AUFNAHMEN=3 if station == 'N' else 1,
                                   COVID=2 if station == 'N' else 1,
                                   INFLUENZA=2 if station == 'N' else 0,
                                   RSV=1 if station == 'N' else 0,
                                   PNEUMOKOKKEN=0, SONSTIGE=1,
                                   BEV_ZAHL=(1000 if sex == 'M' else 2000)
                                   + region_index * 100 + age_index * 10 + week)
                        if mutate:
                            mutate(row)
                        writer.writerow(row)
    return text.getvalue().encode()


def dictionaries(feed):
    return [dict(zip(feed['columns'], row)) for row in feed['rows']]


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture()
        cls.bundle = create_bundle(cls.raw, RETRIEVED)

    def test_title_compatibility_and_latest_weeks(self):
        data = transform(self.raw, RETRIEVED)
        self.assertEqual(data, self.bundle['monitor.json'])
        self.assertEqual(data['version'], 1)
        self.assertEqual(data['metric'], 'AUFNAHMEN')
        self.assertEqual([w['value'] for w in data['weeks']], [576] * 3)
        self.assertEqual([w['provisional'] for w in data['weeks']], [False, True, True])
        self.assertEqual(data['weeks'][0]['date'], '2026-10-01')
        self.assertEqual(data['weeks'][-1]['week'], 42)

    def test_population_is_not_doubled_by_station(self):
        rows = dictionaries(self.bundle['data/austria.json'])
        week = {r['station']: r for r in rows if r['week'] == 40}
        expected_population = sum(1000 + 2000 + 2 * (region * 100 + age * 10 + 40)
                                  for region in range(9) for age in range(8))
        self.assertEqual(week['ALL']['population'], expected_population)
        for station in ['N', 'I']:
            self.assertEqual(week[station]['population'], expected_population)
        for metric in METRICS:
            self.assertEqual(week['ALL'][metric], week['N'][metric] + week['I'][metric])
            self.assertAlmostEqual(week['ALL'][metric + '_per100k'],
                                   week['ALL'][metric] / expected_population * 100000,
                                   places=6)

    def test_age_rate_uses_age_population(self):
        row = next(r for r in dictionaries(self.bundle['data/ages.json'])
                   if r['week'] == 40 and r['age'] == '0 - 4' and r['station'] == 'ALL')
        expected_population = sum(1000 + 2000 + 2 * (region * 100 + 40)
                                  for region in range(9))
        self.assertEqual(row['population'], expected_population)
        self.assertEqual(row['RSV'], 18)
        self.assertAlmostEqual(row['RSV_per100k'], 18 / expected_population * 100000, places=6)

    def test_region_rates_use_region_population(self):
        regions = dictionaries(self.bundle['data/regions.json'])
        selected = [r for r in regions if r['week'] == 40 and r['station'] == 'ALL']
        national = next(r for r in dictionaries(self.bundle['data/austria.json'])
                        if r['week'] == 40 and r['station'] == 'ALL')
        self.assertEqual(len(selected), 9)
        self.assertEqual(sum(r['population'] for r in selected), national['population'])
        for metric in METRICS:
            self.assertEqual(sum(r[metric] for r in selected), national[metric])
        self.assertNotAlmostEqual(sum(r['AUFNAHMEN_per100k'] for r in selected) / 9,
                                  national['AUFNAHMEN_per100k'], places=3)

    def test_overlapping_diagnoses_do_not_inflate_total(self):
        row = next(r for r in dictionaries(self.bundle['data/austria.json'])
                   if r['week'] == 40 and r['station'] == 'ALL')
        self.assertEqual(row['AUFNAHMEN'], 576)
        self.assertGreater(sum(row[k] for k in METRICS[1:]), row['AUFNAHMEN'])

    def test_detail_population_has_no_station_dimension(self):
        detail = self.bundle['data/details.json']
        self.assertEqual(len(detail['admissions']['rows']), 864)
        self.assertEqual(len(detail['population']['rows']), 432)
        self.assertNotIn('station', detail['population']['columns'])
        self.assertEqual(set(r[4] for r in detail['admissions']['rows']), AGES)
        self.assertEqual(set(r[3] for r in detail['admissions']['rows']), {'M', 'W'})

    def test_invalid_source_rejected(self):
        invalid = [
            fixture(mutate=lambda r: r.update(AUFNAHMEN=-1)),
            fixture(mutate=lambda r: r.update(INFLUENZA=-1)),
            fixture(mutate=lambda r: r.update(COVID=4)),
            fixture(mutate=lambda r: r.update(BEV_ZAHL=0)),
            fixture(mutate=lambda r: r.update(BEV_ZAHL=1000 if r['STATION'] == 'N' else 2000)),
            fixture(mutate=lambda r: r.update(WOHNORT='UNKNOWN')),
            fixture(weeks=((2026, 40), (2026, 42), (2026, 43))),
            self.raw + self.raw.splitlines(keepends=True)[1],
            b'wrong;schema\n1;2',
            self.raw.replace(b'BEV_ZAHL', b'NOT_POPULATION', 1),
            b'\n'.join(self.raw.splitlines()[:-1]),
        ]
        for raw in invalid:
            with self.subTest(source=raw[:100]), self.assertRaises(ValueError):
                create_bundle(raw, RETRIEVED)

    def test_iso_year_and_season_boundary(self):
        data = transform(fixture(weeks=((2026, 53), (2027, 1), (2027, 2))), RETRIEVED)
        self.assertEqual([w['season'] for w in data['weeks']], [2026] * 3)
        autumn = transform(fixture(weeks=((2026, 39), (2026, 40), (2026, 41))), RETRIEVED)
        self.assertEqual([w['season'] for w in autumn['weeks']], [2025, 2026, 2026])

    def test_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'monitor.json'
            atomic_json(path, {'value': 1})
            atomic_json(path, {'value': 2})
            self.assertEqual(json.loads(path.read_text()), {'value': 2})
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_failure_keeps_last_valid_feeds(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write_bundle(self.bundle, base / 'monitor.json', base / 'data')
            before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob('*.json')}
            (base / 'bad.csv').write_bytes(b'wrong;schema\n1;2')
            result = subprocess.run([sys.executable, str(BASE / 'import_sari.py'),
                                     '--input', str(base / 'bad.csv'),
                                     '--output', str(base / 'monitor.json')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            for name, content in before.items():
                self.assertEqual((base / name).read_bytes(), content)
            self.assertFalse(json.loads((base / 'status.json').read_text())['ok'])

    def test_regression_keeps_last_valid_feeds(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write_bundle(self.bundle, base / 'monitor.json', base / 'data')
            before = (base / 'monitor.json').read_bytes()
            (base / 'old.csv').write_bytes(fixture(weeks=((2026, 39), (2026, 40), (2026, 41))))
            result = subprocess.run([sys.executable, str(BASE / 'import_sari.py'),
                                     '--input', str(base / 'old.csv'),
                                     '--output', str(base / 'monitor.json')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((base / 'monitor.json').read_bytes(), before)

    def test_build_copies_feeds_and_rejects_mixed_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write_bundle(self.bundle, base / 'monitor.json', base / 'data')
            for filename in ['chart.html', 'chart.css', 'chart.js']:
                (base / filename).write_text((BASE / filename).read_text())
            build(base, 'https://example.org/monitor.json')
            for filename in self.bundle:
                self.assertEqual((base / filename).read_bytes(), (base / 'site' / filename).read_bytes())
            path = base / 'data' / 'ages.json'
            changed = json.loads(path.read_text())
            changed['sourceSha256'] = 'different'
            atomic_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'Mixed data snapshots'):
                build(base, 'https://example.org/monitor.json')


if __name__ == '__main__':
    unittest.main()
