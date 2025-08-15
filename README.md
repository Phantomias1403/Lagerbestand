# Fan-Kultur Xperience Lagerbestandssystem

Dieses Projekt ist ein einfaches Lagerverwaltungssystem für Fanartikel basierend auf Flask und SQLite. Es unterstützt Artikelverwaltung, Lagerbewegungen sowie Import/Export per CSV und eine optionale Benutzerverwaltung.

## Installation

1. Abhängigkeiten installieren:
   ```bash
   pip install flask flask_sqlalchemy flask_login werkzeug fpdf
   ```
   ```bash
   pip install python-dotenv
   ```
2. Anwendung starten:
   ```bash
   python run.py
   ```
3. Im Browser `http://localhost:5000` öffnen.

Die Benutzerverwaltung ist standardmäßig aktiviert. Momentan kann man
sie nicht deaktivieren.
Beim ersten Start mit aktivierter Benutzerverwaltung wird automatisch ein
Admin-Benutzer `admin` mit Passwort `admin` angelegt.

Angemeldete Benutzer können ihr Profil unter "Profil" bearbeiten und dort
Benutzername sowie Passwort ändern.

### Passwort-Reset per E-Mail
Um das Zurücksetzen des Passworts zu ermöglichen, muss ein SMTP-Server
konfiguriert sein. Standardmäßig wird der Gmail‑Server `smtp.gmail.com`
über Port `587` mit TLS verwendet. Es müssen lediglich folgende
Umgebungsvariablen gesetzt werden:

* `MAIL_SERVER` – Adresse des SMTP-Servers (Standard: `smtp.gmail.com`)
* `MAIL_PORT` – Port des Servers (Standard: `587`)
* `MAIL_USERNAME` – Benutzername für die Anmeldung
* `MAIL_PASSWORD` – Passwort für die Anmeldung
* `MAIL_SENDER` – Absenderadresse der E-Mails (Standard: wie `MAIL_USERNAME`)

TLS bzw. SSL wird abhängig vom Port automatisch gewählt. Bei Bedarf kann
dies über die optionalen Variablen `MAIL_USE_TLS` bzw. `MAIL_USE_SSL`
überschrieben werden ("1" für aktiv).
Die Umgebungsvariablen werden in der .env Datei festgelegt.

Nach Einrichtung kann über den Link "Passwort vergessen?" auf der Login-Seite
eine E-Mail mit einem Zurücksetz-Link angefordert werden.


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

In den Einstellungen lassen sich die vorhandenen Kategorien verwalten. Für jede
Kategorie kann dort ein zugehöriger SKU-Prefix, ein Standardpreis und ein
Mindestbestand definiert werden. Diese Angaben werden beim Anlegen neuer Artikel
oder beim CSV‑Import automatisch übernommen.

## CSV-Import
CSV-Dateien müssen die Spalten `name, sku, stock, category, location_primary, location_secondary` besitzen.

## Backup
Über die Routen `/backup/export` und `/backup/import` lassen sich sämtliche Artikel
und Bestellungen als ZIP-Archiv sichern und wiederherstellen. Das Archiv enthält
vier CSV-Dateien: `articles.csv`, `orders.csv`, `order_items.csv` sowie
`invoice_movements.csv`. Die letzte Datei enthält alle Bewegungen, denen eine
Rechnungsnummer zugeordnet wurde.
Der Import legt nicht vorhandene Datensätze neu an und überschreibt vorhandene
Artikel anhand ihrer SKU.

## Datenbank bereinigen
Im Reiter **Allgemein** der Einstellungen gibt es einen Abschnitt, um Teile der
Datenbank zu löschen. Dort kann man auswählen, ob ausschließlich die gespeicherten
Bestellungen, alle Artikel samt Bewegungen oder die komplette Datenbank (ohne
Benutzer und Einstellungen) entfernt werden sollen. Zum Bestätigen muss das
eigene Passwort erneut eingegeben werden.

## Erweiterung
Das System ist modular aufgebaut und lässt sich später um Funktionen wie eine Schnittstelle zu eBay/Etsy erweitern.

## Dark Mode
Die Farben der Bootstrap‑Komponenten werden im Dark Mode leicht angepasst, um besser lesbar zu sein. Eigene Farbanpassungen befinden sich in `app/static/theme.css`.
