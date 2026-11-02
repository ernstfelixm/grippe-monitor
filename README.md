# Grippe-Monitor

Automatischer Import der österreichischen SARI-Krankenhausaufnahmen und eine
direkt in Shorthand einsetzbare Saisonvergleichsgrafik.

## Datenfluss

cron-job.org → GitHub Actions → SARI-CSV → Prüfung → versioniertes JSON → GitHub Pages → Shorthand.

Der Workflow `update.yml` kann manuell und per GitHub-API gestartet werden.
Er enthält bewusst keinen eigenen Zeitplan: Den übernimmt cron-job.org.

## Einrichtung

1. Unter **Settings → Pages → Build and deployment → Source** `GitHub Actions` wählen.
2. Unter **Actions → SARI aktualisieren und veröffentlichen → Run workflow** auf `main` starten.
3. Nach erfolgreichem Lauf steht die tatsächliche Pages-Adresse im Deployment.
   Dort liegen `monitor.json`, `status.json`, `shorthand-section.html` und
   `shorthand-javascript.html` sowie die Vorschau `index.html`.
4. Für cron-job.org einen Fine-grained Personal Access Token erstellen:
   Resource owner = dieses Konto; Repository access = nur `grippe-monitor`;
   Repository permission **Actions: Read and write**. Ablaufdatum festlegen.
   Den Token nur direkt als Authorization-Header bei cron-job.org hinterlegen.
   Niemals in Code, Issues, Screenshots oder Chat einfügen.
5. Cronjob: POST an
   `https://api.github.com/repos/ernstfelixm/grippe-monitor/actions/workflows/update.yml/dispatches`
   mit Headern:
   - `Authorization: Bearer DEIN_TOKEN`
   - `Accept: application/vnd.github+json`
   - `Content-Type: application/json`
   - `X-GitHub-Api-Version: 2026-03-10`
   und Request-Body `{"ref":"main"}`.
6. Zeitplan: Mittwochs um 05:02, Zeitzone **Europe/Vienna**.
   Fehlerbenachrichtigung und Benachrichtigung bei Deaktivierung einschalten.
7. Bei GitHub Benachrichtigungen über fehlgeschlagene Actions-Läufe aktivieren.
   Ein erfolgreicher Cron-Aufruf bestätigt nur den Startauftrag, nicht den
   erfolgreichen Import oder die Veröffentlichung. Der Workflow muss ebenfalls
   erfolgreich enden; die Grafik zeigt einen Hinweis bei veralteten Daten.

Der externe Token startet lediglich den Workflow. Der Workflow selbst verwendet
das kurzlebige, automatisch von GitHub erzeugte `GITHUB_TOKEN` zum Speichern und
Veröffentlichen. Es wird kein Personal Access Token in GitHub benötigt.

## In Shorthand einbauen

Den veröffentlichten Inhalt von `shorthand-section.html` in eine Custom-HTML-Section
kopieren. `shorthand-javascript.html` inklusive Script-Tags in das JS-Feld der Story
kopieren. In der Vorschau prüfen, dann veröffentlichen. Die HTML-Dateien bei einer
späteren Bearbeitung als Quelltext öffnen, nicht die gerenderte Grafik kopieren.

Die Datenadresse wird beim Build automatisch aus der tatsächlichen Pages-Adresse
eingetragen. Danach erscheinen neue Daten ohne erneutes Veröffentlichen der Story.
Beim Seitenaufruf und alle 15 Minuten in sichtbaren Tabs wird geprüft. Bei einem
Abruffehler bleibt der letzte gültige Stand der geöffneten Seite bzw. der eingebettete
Snapshot sichtbar. Ein Fehler- bzw. Altershinweis erscheint. Browser speichern die
geladenen Daten nicht dauerhaft über ein Neuladen hinaus.

Schriften, Größen und Textfarben erbt der Block von Shorthand. Die eigenständige
Vorschau nutzt Arial ausschließlich als umgebende Vorschauschrift. Die Legende ist
anklickbar; exakte Werte, Tastaturbedienung und Methodik stehen unter der Grafik.

## Datenqualität und Archiv

Es werden alle verfügbaren Wochen gezeigt, einschließlich der neuesten beiden
unvollständigen Meldewochen. Der gesamte Bestand wird neu eingelesen, damit ältere
Nachmeldungen einfließen. Struktur, Kategorien, Duplikate, 288 Quellzeilen je Woche,
Zahlenwerte und Wochenfolge werden geprüft. Ein zeitlich zurückgefallener Bestand
wird abgelehnt. Bei einem Fehler wird kein neuer Pages-Stand veröffentlicht.

Erfolgreiche normalisierte Datenstände werden in Git versioniert. Jede veränderte
Quelldatei wird einmal komprimiert unter `archive/<sha256>.csv.gz` gespeichert.
Ein Hash dient der Wiedererkennung; identische Quellen werden nicht mehrfach archiviert.
`retrievedAt` ist der erfolgreiche Abrufzeitpunkt, nicht das Veröffentlichungsdatum der
Quelle. `sourceSha256` identifiziert ihren Inhalt, `weeks` die tatsächlich verfügbaren Wochen.

GitHub Actions und cron-job.org können verzögert starten. Token-Ablauf und fehlgeschlagene
Läufe müssen betreut werden. HTTPS-/CORS-Zugriff von der echten Shorthand-Veröffentlichung
ist nach dem ersten Deployment zu prüfen. Bisherige lokale Prüfungen ersetzen diesen
Test im Zielsystem nicht.

## Lokale Entwicklung

Python 3.9 oder neuer, keine zusätzlichen Pakete:

```sh
python3 -m unittest discover -p 'test_*.py' -v
python3 import_sari.py --output monitor.json --archive-dir archive
python3 build.py
```

Für eine lokale CSV: `python3 import_sari.py --input DATEI.csv --output monitor.json`.
`site/` enthält die erzeugte Vorschau. Beim lokalen Build ohne `--data-url` wird nur
der eingebettete Snapshot verwendet.

## Kennzahl

Gesamte wöchentliche SARI-Aufnahmen (`AUFNAHMEN`), Wohnsitz Österreich,
Normal- und Intensivstationen zusammen. Keine Addition der Diagnosegruppen.
Keine Zahl aller Erkrankten und keine Zahl aktuell belegter Betten.
Wochenwerte werden anhand des Donnerstags auf eine Saisonachse Oktober–September
gelegt. Die erste verfügbare Saison 2022/23 beginnt erst in KW 19/2023.

Quelle: **Statistische Daten des Dachverbandes der Sozialversicherungsträger**.
[Daten und Methodik](https://www.sari-dashboard.at/opendata).


## Erweiterter Datenimport

Der Import liest die vollständige wohnortbezogene Patientendatei: alle Diagnosen,
Altersgruppen, Geschlechter, Bundesländer, Stationsarten und Bevölkerungszahlen.
Der bestehende Feed `monitor.json` für die Titelgrafik bleibt kompatibel und absolut.
Alle neuen normierten Werte beziehen sich auf **100.000 Menschen der jeweiligen
Bevölkerungsgruppe**. Die Krankenhausstandort-Datei wird nicht beigemischt.

Bei jedem erfolgreichen Lauf entstehen zusätzlich:

| Datei unter `data/` | Inhalt |
| --- | --- |
| `index.json` | Datenstand, Wochen, Kategorien, Kennzahlen, Dateiverweise und Methodik |
| `austria.json` | Österreich je Woche, alle Diagnosen, getrennt nach N/I/ALL |
| `ages.json` | Dieselben Werte für jede der acht Altersgruppen |
| `regions.json` | Dieselben Werte für jedes der neun Wohnsitz-Bundesländer |
| `details.json` | Vollständige Aufnahmedaten plus separate Bevölkerung für kombinierte Filter |

Die Pfade gelten relativ zur Pages-Adresse, beispielsweise
`https://ernstfelixm.github.io/grippe-monitor/data/austria.json`.
Die drei kleinen Auswertungsfeeds dienen den Grafiken; die vollständigen Details
müssen nur für kombinierte Filter geladen werden. Die Dateien sind auch vom
späteren Artikel-Dashboard verwendbar. Es ist kein zusätzlicher Cronjob nötig.

### Format und Berechnung

Die Tabellen enthalten `columns` (Spaltennamen) und `rows` (Wertearrays).
Jede Zeile enthält Werte in exakt dieser Spaltenreihenfolge. In JavaScript:

```js
const response = await fetch(DATA_URL);
if (!response.ok) throw new Error(`Datenabruf fehlgeschlagen: ${response.status}`);
const data = await response.json();
const rows = data.rows.map(row =>
  Object.fromEntries(data.columns.map((column, index) => [column, row[index]]))
);
const influenza = rows.filter(row => row.station === "ALL");
// row.INFLUENZA: absolute Aufnahmen; row.INFLUENZA_per100k: Rate.
// Jahr/KW verknüpfen die Werte mit data.weeks (Datum, Saison, vorläufig).
```

- `AUFNAHMEN`, `COVID`, `INFLUENZA`, `RSV`, `PNEUMOKOKKEN`, `SONSTIGE`
  sind absolute wöchentliche Werte. `*_per100k` enthält die jeweilige Rate.
- `population` ist die Bevölkerung derselben Woche und Gruppe aus `BEV_ZAHL`.
  Sie zählt je Region, Geschlecht und Alter nur einmal, auch bei kombinierten
  Stationen. Raten entstehen aus Summen von Aufnahmen und Bevölkerung, nicht
  aus dem Mittelwert von Untergruppenraten.
- `region: AT`, `sex: ALL`, `age: ALL` bezeichnen die zusammengefasste Gruppe.
  In `ages.json` ist `age` die konkrete Altersgruppe, in `regions.json` ist
  `region` das konkrete Wohnsitz-Bundesland.
- `station: ALL` ist bereits die Summe von `N` und `I`. Genau eine Stationsauswahl
  verwenden und diese drei Zeilentypen niemals miteinander summieren.
- `details.json` enthält `admissions.columns/rows` und `population.columns/rows`.
  Die Bevölkerung hat **keine Stationsdimension**. Für einen Filter zuerst
  Aufnahmen und passende Bevölkerungszellen aggregieren, dann dividieren.
- Diagnosegruppen überlappen. `AUFNAHMEN` wird niemals aus anderen Diagnosen
  berechnet. Keine 100-Prozent-Stapel mit vermeintlich exklusiven Gruppen.
- Wochen folgen ISO-Jahr und ISO-KW. Die Saison startet im Oktober, zugeordnet
  nach dem Donnerstag der Woche. `season` ist das Startjahr.
- Die letzten zwei vorhandenen Wochen bleiben sichtbar und sind `provisional`.
  Auch ältere Werte können revidiert werden. `retrievedAt` ist der Abrufzeitpunkt.

Die Raten werden mit sechs Dezimalstellen geliefert; die Anzeige rundet erst im
Diagramm. Alle Feeds tragen denselben `sourceSha256` und `retrievedAt`. Der Build
prüft deren Übereinstimmung. Beim Laden mehrerer Feeds soll der Client beide
Kennungen vergleichen und bei Abweichungen neu laden, weil CDN-Caches einzelne
Dateien zeitversetzt ausliefern können.

Zusätzlich geprüft werden alle Diagnosefelder, positive Bevölkerungszahlen und
identische Bevölkerungszahlen für die zwei Stationszeilen derselben Gruppe.
Einzelne Diagnosen dürfen die Gesamtaufnahmen nicht überschreiten; ihre Summe
darf wegen Mehrfachdiagnosen größer sein. Historische Wochen dürfen nicht fehlen.
Die Tests decken außerdem Bevölkerungsverdoppelung, Alters- und Regionsraten,
Saison- und ISO-Jahresgrenzen, den Erhalt gültiger Daten bei Fehlern sowie den
Pages-Build und die Kompatibilität der absoluten Titelgrafik ab.


## Flourish Live CSV

Der bestehende Workflow erzeugt nach dem JSON-Import mit `python3 export_flourish.py`
sechs öffentliche CSV-Dateien unter `data/flourish/` und veröffentlicht sie gemeinsam
mit den JSON-Feeds. Der Cronjob und seine Berechtigungen bleiben unverändert.

| CSV | Kennzahl |
| --- | --- |
| `gesamt-aufnahmen.csv` | Absolute wöchentliche SARI-Gesamtaufnahmen |
| `influenza-pro100000.csv` | Influenza-Aufnahmen je 100.000 Einwohner |
| `covid-pro100000.csv` | Covid-Aufnahmen je 100.000 Einwohner |
| `rsv-kinder-pro100000.csv` | RSV-Aufnahmen je 100.000 Kinder von 0 bis 4 Jahren |
| `ages-aktuell.csv` | SARI-Aufnahmen der neuesten Woche nach Alter |
| `regions-aktuell.csv` | SARI-Aufnahmen der neuesten Woche nach Wohnsitz-Bundesland |

Beispieladresse: https://ernstfelixm.github.io/grippe-monitor/data/flourish/gesamt-aufnahmen.csv

Für die vier Saisonvergleiche: A = Saisondatum, B:F = fünf rollierende Saisonen,
neueste zuerst; G = Hinweise mit echten ISO-Kalenderwochen und vorläufigem Status.
Der Saisonwechsel verschiebt die Jahrgangsüberschriften innerhalb derselben fünf
Wertespalten. Deshalb Farben nach Spaltenfolge zuordnen (rot, rosa, dreimal grau),
keine jahresgebundenen Farbüberschreibungen oder Legendenreihenfolgen verwenden.
Historische Daten aller Saisonen bleiben im JSON und im Quellenarchiv erhalten.

Die Referenzachse reicht von 2003-10-01 bis 2004-09-30 und enthält den 29. Februar.
Diese Jahreszahlen sind nur technische Positionen: Auf der x-Achse ausschließlich
Monate anzeigen. Werte stehen nur an den übertragenen Wochen-Donnerstagen. Leere
Zellen sind fehlende Beobachtungen, keine Nullen; keine Werte auffüllen. In Flourish
`Missing data points: Continue line` wählen, damit die Wochenpunkte verbunden
werden. Nullwerte bleiben als 0 erhalten. Die letzten beiden Wochen bleiben enthalten.

In Flourish: Data → Connect to live URL → CSV-Adresse → Import. A als Datum erkennen
lassen (`YYYY-MM-DD`), B:F als Werte und G als Zusatzinformation zuordnen.
Nach dem Veröffentlichen im Export-Dialog die automatische Aktualisierung aktivieren.
Die Datenverbindung im Editor allein schaltet die regelmäßige Neuveröffentlichung
noch nicht ein. Verfügbarkeit und Mindestintervall hängen vom Flourish-Tarif ab.
Die Verbindung bleibt dauerhaft an dieselbe CSV-Adresse gebunden.

Die Fußnote darf kein fest eingetragenes Abrufdatum oder eine feste neueste KW
enthalten. Stattdessen den Hinweis auf unvollständige Wochen und bei Bedarf
`{{data_last_updated}}` für den letzten Flourish-Datenabruf verwenden. Das ist nicht
das Veröffentlichungsdatum der SARI-Quelle. Bei Alters- und Bundesland-CSV sind
aktuelle Woche und Unvollständigkeit als eigene Spalten enthalten.

`data/flourish/index.json` nennt Dateinamen, Datenstand und Quellhash. Vor dem
Pages-Build wird die Übereinstimmung mit dem JSON-Datenstand geprüft. Ein Fehler
verhindert die Veröffentlichung. Die zusätzliche Testsuite prüft fehlende Werte,
Nullwerte, Schaltjahr, Saisonwechsel, Altersnenner und gemischte Datenstände.
