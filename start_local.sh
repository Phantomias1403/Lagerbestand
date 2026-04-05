#!/usr/bin/env bash
set -euo pipefail

echo "[Debug] Starte Script..."

# --- Verzeichnis des Scripts ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[Debug] SCRIPT_DIR=$SCRIPT_DIR"

# --- Projektroot automatisch bestimmen ---
if [ -f "$SCRIPT_DIR/requirements.txt" ] && [ -f "$SCRIPT_DIR/lagerbestand_site/manage.py" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/requirements.txt" ] && [ -f "$SCRIPT_DIR/manage.py" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../requirements.txt" ] && [ -f "$SCRIPT_DIR/manage.py" ]; then
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  echo "[Fehler] Konnte Projektroot nicht automatisch bestimmen." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
echo "[Debug] PROJECT_ROOT=$PROJECT_ROOT"

# --- manage.py Pfad bestimmen ---
if [ -f "$PROJECT_ROOT/lagerbestand_site/manage.py" ]; then
  MANAGE_PY="$PROJECT_ROOT/lagerbestand_site/manage.py"
elif [ -f "$PROJECT_ROOT/manage.py" ]; then
  MANAGE_PY="$PROJECT_ROOT/manage.py"
else
  echo "[Fehler] manage.py nicht gefunden." >&2
  exit 1
fi
echo "[Debug] MANAGE_PY=$MANAGE_PY"

# --- System-Python finden ---
# Auf Windows zuerst py probieren, dann python, dann python3
if command -v py >/dev/null 2>&1; then
  SYS_PY="py -3"
elif command -v python >/dev/null 2>&1; then
  SYS_PY="python"
elif command -v python3 >/dev/null 2>&1; then
  SYS_PY="python3"
else
  echo "[Fehler] Weder 'py', 'python' noch 'python3' gefunden." >&2
  exit 1
fi
echo "[Debug] SYS_PY=$SYS_PY"

VENV_DIR="$PROJECT_ROOT/.venv"

# --- Funktion: Python in venv-Pfad ermitteln ---
find_venv_python() {
  if [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    echo "$VENV_DIR/Scripts/python.exe"
    return 0
  elif [ -f "$VENV_DIR/bin/python" ]; then
    echo "$VENV_DIR/bin/python"
    return 0
  fi
  return 1
}

# --- Funktion: venv neu erstellen ---
recreate_venv() {
  echo "[Info] Erstelle virtuelle Umgebung neu ..."
  rm -rf "$VENV_DIR"
  eval "$SYS_PY -m venv \"$VENV_DIR\""
}

# --- venv auf Existenz prüfen ---
if [ ! -d "$VENV_DIR" ]; then
  echo "[Info] Keine .venv gefunden."
  recreate_venv
fi

# --- pyvenv.cfg prüfen ---
if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_DIR/pyvenv.cfg" ]; then
  echo "[Warnung] pyvenv.cfg fehlt. venv ist defekt."
  recreate_venv
fi

# --- Python in venv finden ---
if ! PY="$(find_venv_python)"; then
  echo "[Warnung] Kein Python in .venv gefunden."
  recreate_venv
  PY="$(find_venv_python)"
fi

echo "[Debug] VENV_PY=$PY"

# --- prüfen, ob venv-python wirklich startbar ist ---
if ! "$PY" --version >/dev/null 2>&1; then
  echo "[Warnung] venv-Python ist nicht ausführbar. Die .venv verweist vermutlich auf eine alte Python-Installation."
  recreate_venv
  PY="$(find_venv_python)"
fi

echo "[Debug] VENV_PY_FINAL=$PY"
"$PY" --version

# --- pip sicherstellen ---
"$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PY" -m pip --version

# --- requirements.txt prüfen ---
if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
  echo "[Fehler] requirements.txt nicht gefunden unter $PROJECT_ROOT/requirements.txt" >&2
  exit 1
fi

# --- Abhängigkeiten installieren ---
echo "[Info] Installiere/aktualisiere Python-Abhängigkeiten ..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$PROJECT_ROOT/requirements.txt"

# --- Lokale Umgebungsvariablen setzen ---
export DB_ENGINE="${DB_ENGINE:-django.db.backends.sqlite3}"
export DB_NAME="${DB_NAME:-$PROJECT_ROOT/db.sqlite3}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-local-secret-key}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"
export ENV="${ENV:-local}"

echo "[Debug] DB_ENGINE=$DB_ENGINE"
echo "[Debug] DB_NAME=$DB_NAME"
echo "[Debug] ENV=$ENV"

# --- Migrationen ---
echo "[Info] Führe Migrationen aus ..."
"$PY" "$MANAGE_PY" migrate --verbosity 2

# --- Entwicklungsserver starten ---
ADDR_PORT="${RUNSERVER_ADDR_PORT:-127.0.0.1:8000}"
echo "[Info] Starte Django-Server auf ${ADDR_PORT} ..."
exec "$PY" "$MANAGE_PY" runserver "$ADDR_PORT"