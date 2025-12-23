#!/usr/bin/env bash
# Automatischer Helfer zum lokalen Start der Lagerbestand-Webseite.
# Erstellt (falls nötig) eine virtuelle Umgebung, installiert Abhängigkeiten,
# setzt lokale Umgebungsvariablen, führt Migrationen aus und startet Django.

set -euo pipefail

# --- Projektverzeichnis bestimmen ---
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# --- Python-Binary finden (python3 oder python) ---
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[Fehler] Weder 'python3' noch 'python' gefunden. Bitte Python 3 installieren." >&2
  exit 1
fi

# --- Virtuelle Umgebung vorbereiten ---
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "[Info] Virtuelle Umgebung wird unter $VENV_DIR erstellt ..."
  "$PY" -m venv "$VENV_DIR"
fi

# --- Virtuelle Umgebung aktivieren (Windows oder Unix) ---
if [ -f "$VENV_DIR/Scripts/activate" ]; then
  # Windows / Git Bash
  # shellcheck disable=SC1090
  source "$VENV_DIR/Scripts/activate"
elif [ -f "$VENV_DIR/bin/activate" ]; then
  # Linux / macOS
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
else
  echo "[Fehler] Konnte die virtuelle Umgebung nicht aktivieren – keine activate-Datei gefunden." >&2
  exit 1
fi

# --- Abhängigkeiten installieren ---
echo "[Info] Python-Abhängigkeiten werden installiert/aktualisiert ..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# --- Lokale Entwicklungs-Umgebungsvariablen ---
export DB_ENGINE="${DB_ENGINE:-django.db.backends.sqlite3}"
export DB_NAME="${DB_NAME:-${PROJECT_ROOT}/db.sqlite3}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-local-secret-key}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"

# --- Migrationen anwenden ---
echo "[Info] Führe Datenbankmigrationen aus ..."
"$PY" lagerbestand_site/manage.py migrate

# --- Django-Entwicklungsserver starten ---
ADDR_PORT="${RUNSERVER_ADDR_PORT:-127.0.0.1:8000}"
echo "[Info] Starte Django-Server auf ${ADDR_PORT} ..."
exec "$PY" lagerbestand_site/manage.py runserver "$ADDR_PORT"
