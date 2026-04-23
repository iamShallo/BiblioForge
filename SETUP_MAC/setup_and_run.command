#!/bin/bash

# BiblioForge - macOS double-click launcher (.command)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Support both distributed ZIP layout and repository layout.
if [ -d "$SCRIPT_DIR/../BiblioForge" ]; then
  cd "$SCRIPT_DIR/../BiblioForge"
elif [ -f "$SCRIPT_DIR/../main.py" ]; then
  cd "$SCRIPT_DIR/.."
else
  echo "[ERROR] Cartella progetto non trovata."
  echo "Atteso: ../BiblioForge oppure ../main.py"
  read -n 1 -s -r -p "Premi un tasto per chiudere..."
  echo
  exit 1
fi

echo
echo "========================================"
echo "  BiblioForge - Setup e Avvio (macOS)"
echo "========================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python3 non trovato nel PATH"
  echo "Installa Python da https://www.python.org/"
  read -n 1 -s -r -p "Premi un tasto per chiudere..."
  echo
  exit 1
fi

echo "[1/4] Python trovato: $(python3 --version 2>&1)"

if [ -d ".venv" ]; then
  echo "[2/4] Ambiente virtuale già presente"
else
  echo "[2/4] Creazione ambiente virtuale..."
  python3 -m venv .venv
fi

echo "[3/4] Installazione dipendenze..."
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] Avvio dashboard su http://localhost:8501"
echo "Premi Ctrl+C per fermare il programma"
echo
python main.py dashboard

echo
echo "BiblioForge è stato chiuso."
read -n 1 -s -r -p "Premi un tasto per chiudere..."
echo
