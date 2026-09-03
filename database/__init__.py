"""Package per la gestione dello strato dati SQLite."""
from .db_setup import init_db
from .db_manager import DatabaseManager

__all__ = ["init_db", "DatabaseManager"]
