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
