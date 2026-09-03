# Bot Turni di Pulizia 🏠✨

Bot Telegram modulare e asincrono sviluppato con `python-telegram-bot` (v20+), `APScheduler` (tramite PTB JobQueue) e `aiosqlite` per la gestione e notifica dei turni di pulizia della casa.

## 📁 Struttura del Progetto

```plaintext
bot_turni/
├── .env.example              # Template variabili d'ambiente
├── .gitignore                # Regole di esclusione Git
├── README.md                 # Documentazione del progetto
├── requirements.txt          # Dipendenze Python
├── config.py                 # Caricamento configurazioni (.env)
├── main.py                   # Entry point del bot
├── database/
│   ├── __init__.py
│   ├── db_setup.py           # Inizializzazione schema SQLite e mansioni di default
│   └── db_manager.py         # Interfaccia CRUD asincrona
├── handlers/
│   ├── __init__.py
│   ├── start_handler.py      # Gestione /start e /help con auto-registrazione
│   └── shifts_handler.py     # Gestione /turni e /fatto <ID>
├── scheduler/
│   ├── __init__.py
│   └── scheduler_jobs.py     # Task pianificati (promemoria orari/giornalieri)
└── utils/
    ├── __init__.py
    └── helpers.py            # Utility di formattazione ed escaping markdown
```

## 🚀 Istruzioni di Avvio

### 1. Creare l'ambiente virtuale
```bash
python -m venv venv
# Su Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Su Linux/macOS:
source venv/bin/activate
```

### 2. Installare le dipendenze
```bash
pip install -r requirements.txt
```

### 3. Configurare le variabili d'ambiente
Crea una copia di `.env.example` rinominandola in `.env`:
```bash
cp .env.example .env
```
Apri `.env` e inserisci il token ottenuto da [@BotFather](https://t.me/BotFather):
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_PATH=bot_turni.db
TIMEZONE=Europe/Rome
```

### 4. Avviare il bot
```bash
python main.py
```
Il database SQLite verrà inizializzato automaticamente al primo avvio tramite l'hook asincrono `post_init`.
