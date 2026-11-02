import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from export_flourish import export, seasons_csv
from import_sari import create_bundle, write_bundle
from test_import import fixture, RETRIEVED


class FlourishTests(unittest.TestCase):
    def test_dates_missing_values_and_incomplete_weeks(self):
        bundle = create_bundle(fixture(), RETRIEVED)
        weeks = bundle['monitor.json']['weeks']
        text = seasons_csv(weeks, {(w['year'], w['week']): w['value'] for w in weeks})
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 366)
        self.assertEqual(rows[0]['Saisondatum'], '2003-10-01')
        self.assertEqual(rows[-1]['Saisondatum'], '2004-09-30')
        self.assertEqual(list(rows[0])[1:3], ['2026/27', '2025/26'])
        self.assertEqual(rows[0]['2026/27'], '576')
        self.assertEqual(rows[1]['2026/27'], '')
        self.assertEqual(sum(bool(r['2026/27']) for r in rows), 3)
        self.assertIn('unvollständige', rows[7]['Hinweis'])
        self.assertNotIn('unvollständige', rows[0]['Hinweis'])

    def test_leap_day_is_retained(self):
        weeks = [{'year': 2024, 'week': 9, 'date': '2024-02-29', 'season': 2023, 'provisional': True}]
        rows = list(csv.DictReader(io.StringIO(seasons_csv(weeks, {(2024, 9): 0}))))
        row = next(r for r in rows if r['Saisondatum'] == '2004-02-29')
        self.assertEqual(row['2023/24'], '0')

    def test_season_rollover_keeps_five_value_columns(self):
        weeks = [{'year': 2027, 'week': 40, 'date': '2027-10-07', 'season': 2027, 'provisional': True}]
        rows = list(csv.reader(io.StringIO(seasons_csv(weeks, {(2027, 40): 42}))))
        self.assertEqual(rows[0], ['Saisondatum', '2027/28', '2026/27', '2025/26', '2024/25', '2023/24', 'Hinweis'])
        self.assertEqual(rows[7][1], '42')

    def test_all_feeds_and_age_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bundle = create_bundle(fixture(), RETRIEVED)
            write_bundle(bundle, base/'monitor.json', base/'data')
            manifest = export(base)
            self.assertEqual(len(manifest['files']), 6)
            out = base/'data/flourish'
            rsv = list(csv.DictReader(io.StringIO((out/'rsv-kinder-pro100000.csv').read_text())))
            age_feed = bundle['data/ages.json']
            row = next(dict(zip(age_feed['columns'], r)) for r in age_feed['rows']
                       if r[1] == 40 and r[4] == '0 - 4' and r[5] == 'ALL')
            self.assertAlmostEqual(float(rsv[0]['2026/27']), row['RSV_per100k'])
            self.assertEqual(len(list(csv.DictReader(io.StringIO((out/'ages-aktuell.csv').read_text())))), 8)
            self.assertEqual(len(list(csv.DictReader(io.StringIO((out/'regions-aktuell.csv').read_text())))), 9)
            old = (out/'gesamt-aufnahmen.csv').read_bytes()
            wrong = bundle['data/ages.json']; wrong['sourceSha256'] = 'different'
            (base/'data/ages.json').write_text(json.dumps(wrong))
            with self.assertRaisesRegex(ValueError, 'Mixed source snapshots'):
                export(base)
            self.assertEqual((out/'gesamt-aufnahmen.csv').read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
