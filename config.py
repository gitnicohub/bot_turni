import os
from pathlib import Path
from dotenv import load_dotenv

# Percorso base del progetto
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# Carica il file .env se presente
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

# Configurazione Bot Telegram
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configurazione Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "bot_turni.db"))

# Fuso orario per lo scheduler
TIMEZONE = os.getenv("TIMEZONE", "Europe/Rome")

# Coinquilini registrabili tramite /start (ordine = ordine di rotazione dei turni)
ROOMMATES = [
    "Miguel de Segantes",
    "Giorgio Masturbo",
    "Giuseppe Pio Stigmate",
    "Cristiana Turbolenti",
    os.getenv("QUINTO_COINQUILINO", "Quinto Coinquilino (da definire)"),
]

# Cartella da cui viene pescata a caso l'immagine "punitiva" inviata insieme
# all'insulto goliardico quando un turno viene segnato come Non completato.
# Basta copiare i file immagine (.jpg, .jpeg, .png, .gif, .webp) in questa cartella.
PUNISHMENT_IMAGES_DIR = os.getenv("PUNISHMENT_IMAGES_DIR") or str(
    BASE_DIR / "assets" / "punishment_images"
)
