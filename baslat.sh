#!/usr/bin/env bash
# AutoSell - macOS/Linux baslatici: ilk seferde her seyi kurar, sonra paneli acar.
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "[AutoSell] Python 3.10 veya ustu gerekli: https://www.python.org/downloads/"
  exit 1
fi
[ -x .venv/bin/python ] || { echo "[AutoSell] Ilk kurulum yapiliyor..."; "$PY" -m venv .venv; }
if ! cmp -s pyproject.toml .venv/kurulum-pyproject.toml; then
  echo "[AutoSell] Gerekli paketler kuruluyor..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
  .venv/bin/python -m playwright install chromium
  cp pyproject.toml .venv/kurulum-pyproject.toml
fi
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env; }
echo "[AutoSell] Panel aciliyor: http://127.0.0.1:8000  (kapatmak icin Ctrl+C)"
exec .venv/bin/python -m autosell panel --ac
