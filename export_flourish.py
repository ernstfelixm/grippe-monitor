"""Build public Live CSV feeds for Flourish from the validated JSON snapshots."""
import csv
import datetime as dt
import io
import json
from pathlib import Path

from import_sari import atomic_json


def csv_text(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def season_label(year):
    return str(year) + '/' + str(year + 1)[-2:]


def seasons_csv(weeks, values):
    """Five rolling seasons, current first. Blanks are absent readings, never zero."""
    seasons = list(range(weeks[-1]['season'], weeks[-1]['season'] - 5, -1))
    readings, notes = {}, {}
    for week in weeks:
        if week['season'] not in seasons:
            continue
        date = dt.date.fromisoformat(week['date'])
        axis = dt.date(2003 if date.month >= 10 else 2004, date.month, date.day)
        key = (axis, week['season'])
        if key in readings:
            raise ValueError('Two observations map to the same season date')
        readings[key] = values[week['year'], week['week']]
        note = season_label(week['season']) + ': KW ' + str(week['week']) + '/' + str(week['year'])
        if week['provisional']:
            note += ' (unvollständige Meldewoche)'
        notes.setdefault(axis, []).append(note)
    rows = []
    for offset in range(366):
        axis = dt.date(2003, 10, 1) + dt.timedelta(days=offset)
        rows.append([axis.isoformat(), *[readings.get((axis, season), '') for season in seasons],
                     '; '.join(notes.get(axis, []))])
    return csv_text(['Saisondatum', *map(season_label, seasons), 'Hinweis'], rows)


def objects(data):
    return [dict(zip(data['columns'], row)) for row in data['rows']]


def export(base):
    base = Path(base)
    monitor = json.loads((base / 'monitor.json').read_text())
    feeds = {name: json.loads((base / 'data' / (name + '.json')).read_text())
             for name in ['austria', 'ages', 'regions']}
    for feed in feeds.values():
        if any(feed[key] != monitor[key] for key in ['sourceSha256', 'retrievedAt']):
            raise ValueError('Mixed source snapshots for Flourish CSV')
    weeks = monitor['weeks']
    texts = {'gesamt-aufnahmen.csv': seasons_csv(weeks, {
        (week['year'], week['week']): week['value'] for week in weeks})}
    national = [row for row in objects(feeds['austria']) if row['station'] == 'ALL']
    children = [row for row in objects(feeds['ages']) if row['station'] == 'ALL' and row['age'] == '0 - 4']
    for filename, metric, rows in [
        ('influenza-pro100000.csv', 'INFLUENZA', national),
        ('covid-pro100000.csv', 'COVID', national),
        ('rsv-kinder-pro100000.csv', 'RSV', children),
    ]:
        texts[filename] = seasons_csv(weeks, {
            (row['year'], row['week']): row[metric + '_per100k'] for row in rows})
    latest = weeks[-1]
    for name, dimension, label in [('ages', 'age', 'Altersgruppe'), ('regions', 'region', 'Bundesland')]:
        rows = [row for row in objects(feeds[name]) if row['station'] == 'ALL'
                and (row['year'], row['week']) == (latest['year'], latest['week'])]
        texts[name + '-aktuell.csv'] = csv_text(
            [label, 'Aufnahmen je 100000', 'Aufnahmen', 'Bevoelkerung', 'Kalenderwoche', 'Hinweis'],
            [[row[dimension], row['AUFNAHMEN_per100k'], row['AUFNAHMEN'], row['population'],
              'KW ' + str(latest['week']) + '/' + str(latest['year']),
              'Unvollständige Meldewoche' if latest['provisional'] else 'Vorläufige Daten'] for row in rows])
    manifest = {
        'version': 1, 'sourceSha256': monitor['sourceSha256'], 'retrievedAt': monitor['retrievedAt'],
        'latestWeek': latest, 'files': list(texts),
        'seasonColumns': 'Five rolling seasons in columns B:F, newest first; G contains source-week notes',
        'seasonAxis': '2003-10-01 through 2004-09-30; source ISO-week Thursdays by month/day',
        'missing': 'Blank means absent; 0 is an observed zero. Do not replace blanks with zero.',
        'station': 'ALL (Normal- und Intensivstationen)',
        'sourceCredit': monitor['sourceCredit'],
    }
    # Serialize every result before touching public outputs.
    output = base / 'data' / 'flourish'
    output.mkdir(parents=True, exist_ok=True)
    import tempfile
    import os
    with tempfile.TemporaryDirectory(dir=output, prefix='.export-') as directory:
        staging = Path(directory)
        for name, text in texts.items():
            (staging / name).write_text(text, encoding='utf-8')
        atomic_json(staging / 'index.json', manifest)
        for name in texts:
            os.replace(staging / name, output / name)
        os.replace(staging / 'index.json', output / 'index.json')
    print('Flourish:', len(texts), 'CSV feeds, latest KW', latest['week'], '/', latest['year'])
    return manifest


if __name__ == '__main__':
    export(Path(__file__).parent)
