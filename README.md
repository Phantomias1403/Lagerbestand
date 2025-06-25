# Fan-Kultur Xperience Lagerbestandssystem

Dieses Projekt ist ein einfaches Lagerverwaltungssystem für Fanartikel basierend auf Flask und SQLite. Es unterstützt Artikelverwaltung, Lagerbewegungen sowie Import/Export per CSV und eine optionale Benutzerverwaltung.

## Installation

1. Abhängigkeiten installieren:
   ```bash
   pip install flask flask_sqlalchemy flask_login werkzeug fpdf
   ```
2. Anwendung starten:
   ```bash
   python run.py
   ```
3. Im Browser `http://localhost:5000` öffnen.

Die Benutzerverwaltung ist standardmäßig deaktiviert. Soll sie genutzt werden,
kann sie über die Umgebungsvariable `ENABLE_USER_MANAGEMENT=1` aktiviert werden.
Beim ersten Start mit aktivierter Benutzerverwaltung wird automatisch ein
Admin-Benutzer `admin` mit Passwort `admin` angelegt.

Jeder Artikel besitzt nun einen optionalen Mindestbestand. Im Dashboard wird
ein Artikel rot markiert, sobald sein aktueller Lagerbestand unter diesen Wert
fällt. Bei Bewegungen erscheint zudem eine Warnung, wenn der Bestand nach einer
Änderung unter den Mindestbestand sinkt.

Bewegungen können verschiedene Typen wie "Wareneingang" oder "Verlust"
besitzen. Dieser Typ wird in der Historie sowie im CSV‑Export mit aufgeführt.


Bei Bestellungen wird der Lagerbestand der enthaltenen Artikel automatisch
reduziert, sofern die Bestellung den Status "offen" oder "bezahlt" besitzt. Die
Abgänge werden als Warenausgang in den Lagerbewegungen vermerkt.

Über die Detailansicht einer Bestellung kann zudem ein PDF-Versandetikett
erstellt werden (ab Status "bezahlt"). Das Etikett hat nun das Format 100 x 50 mm
und enthält den standardmäßigen Absender
"Fan-Kultur Xperience GmbH, Hauptstr. 20, 55288 Armsheim".

## CSV-Import
CSV-Dateien müssen die Spalten `name, sku, stock, category, location_primary, location_secondary` besitzen.

## Erweiterung
Das System ist modular aufgebaut und lässt sich später um Funktionen wie eine Schnittstelle zu eBay/Etsy erweitern.
