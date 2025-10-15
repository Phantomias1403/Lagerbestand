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
