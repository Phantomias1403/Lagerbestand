# Fan-Kultur Xperience Lagerbestandssystem

Dieses Projekt ist ein einfaches Lagerverwaltungssystem für Fanartikel basierend auf Flask und SQLite. Es unterstützt Artikelverwaltung, Lagerbewegungen sowie Import/Export per CSV und eine optionale Benutzerverwaltung.

## Installation

1. Abhängigkeiten installieren:
   ```bash
   pip install flask flask_sqlalchemy flask_login werkzeug
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

## CSV-Import
CSV-Dateien müssen die Spalten `name, sku, stock, category, location_primary, location_secondary` besitzen.

## Erweiterung
Das System ist modular aufgebaut und lässt sich später um Funktionen wie eine Schnittstelle zu eBay/Etsy erweitern.