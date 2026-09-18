#!/usr/bin/env bash
# Setup del Bot Turni su una VM Debian/Ubuntu (es. GCP e2-micro Always Free).
# Va eseguito come utente "botturni" dentro ~/bot_turni (repo già clonato).
#
# Uso:
#   git clone https://github.com/gitnicohub/bot_turni.git
#   cd bot_turni
#   bash deploy/setup_vm.sh

set -euo pipefail

if [ ! -f "main.py" ]; then
    echo "Esegui questo script dalla root del repo (dove si trova main.py)." >&2
    exit 1
fi

echo "== Installazione dipendenze di sistema =="
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

echo "== Creazione virtual environment =="
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "== Creazione .env da template =="
    cp .env.example .env
    echo
    echo "!! Apri .env (es. 'nano .env') e inserisci il TELEGRAM_BOT_TOKEN prima di avviare il servizio."
fi

echo "== Installazione servizio systemd =="
sudo cp deploy/bot-turni.service /etc/systemd/system/bot-turni.service
sudo systemctl daemon-reload
sudo systemctl enable bot-turni.service

echo
echo "Setup completato."
echo "Se non l'hai ancora fatto, configura .env poi avvia il bot con:"
echo "  sudo systemctl start bot-turni"
echo "  sudo systemctl status bot-turni"
echo "  journalctl -u bot-turni -f    # log in tempo reale"
