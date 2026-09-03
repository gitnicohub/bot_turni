import aiosqlite
import logging
from config import DATABASE_PATH, ROOMMATES

logger = logging.getLogger(__name__)

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS cleaning_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);
"""

CREATE_SHIFTS_TABLE = """
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    scheduled_date DATE NOT NULL,
    is_completed INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    notified INTEGER DEFAULT 0,
    FOREIGN KEY (task_id) REFERENCES cleaning_tasks (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE (task_id, scheduled_date)
);
"""

# I 5 turni della casa, in ordine fisso: l'ordine determina la mappatura
# sui giorni Lun-Ven nella generazione ciclica settimanale (vedi db_manager.compute_week_assignments)
DEFAULT_TASKS = [
    ("bagno1", "Pulizia bagno 1: sanitari, doccia e specchio"),
    ("bagno2", "Pulizia bagno 2: sanitari, doccia e specchio"),
    ("cucina", "Pulizia fornelli, piano lavoro, lavello e pavimento cucina"),
    ("corridoio", "Pulizia e riordino del corridoio e delle aree comuni"),
    ("infrasettimanale", "Giro di pulizia extra infrasettimanale della cucina"),
]

async def init_db():
    """Crea le tabelle nel database SQLite e popola mansioni e coinquilini di default."""
    logger.info("Inizializzazione database SQLite su: %s", DATABASE_PATH)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(CREATE_USERS_TABLE)
        await db.execute(CREATE_TASKS_TABLE)
        await db.execute(CREATE_SHIFTS_TABLE)

        # Popolamento iniziale mansioni predefinite
        for name, desc in DEFAULT_TASKS:
            await db.execute(
                "INSERT OR IGNORE INTO cleaning_tasks (name, description) VALUES (?, ?)",
                (name, desc)
            )

        # Popolamento iniziale coinquilini (senza telegram_id: verrà associato via /start)
        for name in ROOMMATES:
            await db.execute(
                "INSERT OR IGNORE INTO users (name) VALUES (?)",
                (name,)
            )

        await db.commit()
    logger.info("Database inizializzato con successo.")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
