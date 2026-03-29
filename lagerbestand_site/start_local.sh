#!/usr/bin/env bash
set -euo pipefail

echo "[Debug] Starte Script..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
echo "[Debug] PROJECT_ROOT=$PROJECT_ROOT"

if command -v python3 >/dev/null 2>&1; then
  SYS_PY=python3
elif command -v python >/dev/null 2>&1; then
  SYS_PY=python
else
  echo "[Fehler] Weder 'python3' noch 'python' gefunden." >&2
  exit 1
fi
echo "[Debug] SYS_PY=$SYS_PY"

VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "[Info] Erstelle virtuelle Umgebung unter $VENV_DIR ..."
  "$SYS_PY" -m venv "$VENV_DIR"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
  PY="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PY="$VENV_DIR/Scripts/python.exe"
else
  echo "[Fehler] Kein Python in der virtuellen Umgebung gefunden." >&2
  exit 1
fi

echo "[Debug] VENV_PY=$PY"
"$PY" --version

if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
  echo "[Fehler] requirements.txt nicht gefunden unter: $PROJECT_ROOT/requirements.txt" >&2
  exit 1
fi

if [ ! -f "$PROJECT_ROOT/lagerbestand_site/manage.py" ]; then
  echo "[Fehler] manage.py nicht gefunden unter: $PROJECT_ROOT/lagerbestand_site/manage.py" >&2
  exit 1
fi

echo "[Info] Installiere/aktualisiere Python-Abhängigkeiten ..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$PROJECT_ROOT/requirements.txt"

export DB_ENGINE="${DB_ENGINE:-django.db.backends.sqlite3}"
export DB_NAME="${DB_NAME:-${PROJECT_ROOT}/db.sqlite3}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-local-secret-key}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"

echo "[Debug] DB_ENGINE=$DB_ENGINE"
echo "[Debug] DB_NAME=$DB_NAME"

echo "[Info] Führe Migrationen aus ..."
"$PY" "$PROJECT_ROOT/lagerbestand_site/manage.py" migrate --verbosity 2

ADDR_PORT="${RUNSERVER_ADDR_PORT:-127.0.0.1:8000}"
echo "[Info] Starte Django-Server auf ${ADDR_PORT} ..."
exec "$PY" "$PROJECT_ROOT/lagerbestand_site/manage.py" runserver "$ADDR_PORT"