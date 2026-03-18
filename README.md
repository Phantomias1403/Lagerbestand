# Fan-Kultur Xperience Lagerbestandssystem (Django Edition)

Dieses Projekt ist eine professionelle Neuumsetzung des Lagerverwaltungssystems
auf Basis von **Django** und einer relationalen Datenbank wie MySQL. Alle
Funktionen der ursprünglichen Anwendung – Artikelverwaltung, Bewegungen,
Bestellungen, CSV-Import/-Export, Backups sowie optionale Benutzerverwaltung –
stehen weiterhin zur Verfügung, wurden aber vollständig auf eine
Hostinger-kompatible Architektur umgestellt.

## Installation

1. Abhängigkeiten installieren (z. B. in einem virtuellen Environment):
   ```bash
   pip install -r requirements.txt
   ```
2. Datenbankverbindung über Umgebungsvariablen konfigurieren:
   ```bash
   export DB_ENGINE="django.db.backends.mysql"
   export DB_NAME="lagerbestand"
   export DB_USER="<db-user>"
   export DB_PASSWORD="<db-pass>"
   export DB_HOST="<db-host>"
   export DB_PORT="3306"
   export DJANGO_SECRET_KEY="<random-secret>"
   export DJANGO_ALLOWED_HOSTS="example.com,www.example.com"
   ```
   Für lokale Entwicklung kann `DB_ENGINE="django.db.backends.sqlite3"`
   gesetzt werden.
3. Datenbanktabellen anlegen:
   ```bash
   python lagerbestand_site/manage.py migrate
   ```
4. Administrationszugang anlegen:
   ```bash
   python lagerbestand_site/manage.py createsuperuser
   ```
5. Entwicklungsserver starten:
   ```bash
   python lagerbestand_site/manage.py runserver
   ```

### SQLite-Schnellstart (lokal)
Für einen schnellen lokalen Start ohne Datenbank-Setup kannst du SQLite nutzen. Dadurch entfällt die Host-Auflösung auf „postgres“.

* Windows PowerShell:
  ```powershell
  $env:DB_ENGINE="django.db.backends.sqlite3"; python lagerbestand_site/manage.py migrate; python lagerbestand_site/manage.py runserver
  ```
* Windows-Eingabeaufforderung (cmd):
  ```cmd
  set DB_ENGINE=django.db.backends.sqlite3 && python lagerbestand_site/manage.py migrate && python lagerbestand_site/manage.py runserver
  ```
* macOS/Linux:
  ```bash
  DB_ENGINE=django.db.backends.sqlite3 python lagerbestand_site/manage.py migrate && python lagerbestand_site/manage.py runserver
  ```

## Tests

Die Anwendung verwendet Django-Tests. Sie lassen sich mit folgendem Befehl
starten:
```bash
python lagerbestand_site/manage.py test
```

## Deployment auf Hostinger

* Django-App via Gunicorn und Hostinger Python Hosting bereitstellen.
* Statische Dateien mit `python lagerbestand_site/manage.py collectstatic`
  bündeln und über den Webserver ausliefern.
* MySQL-Datenbank in Hostinger anlegen und die oben genannten Variablen setzen.
* Für den Mailversand können die SMTP-Einstellungen des Providers über
  `MAIL_*`-Variablen hinterlegt werden.

Weitere Details zur Konfiguration der Lagerlogik finden sich im Code der
Applikation innerhalb des Verzeichnisses `lagerbestand_site/core`.

## Amazon-Bestellungen (SP-API)

* Neue Modelle und Admin-Ansichten befinden sich im App-Modul `lagerbestand_site/amazon`.
* Import-Logik und Management Command: `python lagerbestand_site/manage.py import_amazon_orders`.
* Die importierten Amazon-Bestellungen werden in der bestehenden Bestellübersicht angezeigt.

Erforderliche Umgebungsvariablen (siehe `.env.example`):

```
AMAZON_CLIENT_ID
AMAZON_CLIENT_SECRET
AMAZON_REFRESH_TOKEN
```
export DB_ENGINE=django.db.backends.sqlite3
export DJANGO_DEBUG=1
python lagerbestand_site/manage.py migrate
python lagerbestand_site/manage.py runserver



## Easybill-Bestellungen

* In den API-Import-Einstellungen gibt es nun einen eigenen Easybill-Import mit Verbindungs-Test.
* Der Import holt die neuesten Bestellungen und legt/aktualisiert diese in der Bestellübersicht.
* Beim Import wird der Lagerbestand automatisch anhand der importierten Positionen über Bewegungen angepasst.

Erforderliche Umgebungsvariablen:

```
EASYBILL_API_KEY
EASYBILL_USER_ID
# optional:
IMPORT_MANAGER_USER_ID=<import-manager-user-id>
EASYBILL_API_URL=https://import.easybill.de/api/v1
EASYBILL_ORDERS_ENDPOINT=/orders
```
