import csv
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from import_sari import transform,atomic_json,REGIONS,AGES

def fixture():
    text=io.StringIO();writer=csv.writer(text,delimiter=';')
    writer.writerow(['JAHR','KW','WOHNORT','GESCHLECHT','ALTERSGRUPPE','STATION','AUFNAHMEN'])
    for week in [40,41,42]:
        for r in sorted(REGIONS):
            for g in ['M','W']:
                for a in sorted(AGES):
                    for s in ['N','I']:writer.writerow([2026,week,r,g,a,s,1])
    return text.getvalue().encode()

class ImportTests(unittest.TestCase):
    def test_all_latest_weeks(self):
        data=transform(fixture(),'2026-10-30T00:00:00Z')
        self.assertEqual([w['value'] for w in data['weeks']],[288,288,288])
        self.assertEqual([w['provisional'] for w in data['weeks']],[False,True,True])
        self.assertEqual(data['weeks'][-1]['week'],42)
        self.assertEqual(data['weeks'][0]['date'],'2026-10-01')
    def test_duplicate_and_changed_schema(self):
        raw=fixture()
        with self.assertRaises(ValueError):transform(raw+raw.splitlines(keepends=True)[1],'2026-10-30T00:00:00Z')
        with self.assertRaises(ValueError):transform(b'wrong;schema\n1;2','2026-10-30T00:00:00Z')
    def test_negative(self):
        raw=fixture().replace(b';N;1',b';N;-1',1)
        with self.assertRaises(ValueError):transform(raw,'2026-10-30T00:00:00Z')
    def test_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'monitor.json';atomic_json(p,{'value':1});atomic_json(p,{'value':2})
            self.assertEqual(json.loads(p.read_text()),{'value':2})
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])
    def test_real_snapshot(self):
        data=json.loads(Path(__file__).with_name('monitor.json').read_text())
        self.assertGreaterEqual(len(data['weeks']),180)
        dates=[dt.date.fromisoformat(w['date']) for w in data['weeks']]
        self.assertTrue(all((b-a).days==7 for a,b in zip(dates,dates[1:])))
        self.assertTrue(all(w['value']>=0 for w in data['weeks']))

if __name__=='__main__':unittest.main()
