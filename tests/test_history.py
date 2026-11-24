import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
import handlers.shifts_handler as sh
from database.db_manager import DatabaseManager
from utils.helpers import format_user_history

TODAY = date(2026, 11, 25)  # mercoledì
MONDAY = date(2026, 11, 23)
TG_ID = 111


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "history.db")
    monkeypatch.setattr(dbm, "DATABASE_PATH", path)
    monkeypatch.setattr(dbs, "DATABASE_PATH", path)
    run(dbs.init_db())

    async def seed():
        async with aiosqlite.connect(path) as conn:
            await conn.execute("UPDATE users SET telegram_id = ? WHERE id = 1;", (TG_ID,))
            # (task, user, data, fatto, completed_at UTC, recuperato)
            rows = [
                (1, 1, MONDAY - timedelta(days=14), 1, "2026-11-10 22:30:00", 0),  # fatto
                (2, 1, MONDAY - timedelta(days=7), 0, None, 0),                    # mancato
                (3, 1, MONDAY - timedelta(days=21), 1, "2026-11-04 23:30:00", 1),  # recuperato, 23:30 UTC = 00:30 del giorno dopo
                (4, 1, MONDAY + timedelta(days=2), 0, None, 0),                    # in attesa
                (1, 2, MONDAY - timedelta(days=7), 1, "2026-11-17 10:00:00", 0),   # di un altro utente
            ]
            for task, user, day, done, at, rec in rows:
                await conn.execute(
                    "INSERT INTO shifts (task_id, user_id, scheduled_date, is_completed, completed_at, recovered)"
                    " VALUES (?, ?, ?, ?, ?, ?);",
                    (task, user, day.isoformat(), done, at, rec),
                )
            trash = [
                (1, 1, MONDAY - timedelta(days=7), 1, "2026-11-22 09:00:00"),
                (2, 1, MONDAY - timedelta(days=14), 0, None),
                (3, 1, MONDAY, 0, None),
                (4, 2, MONDAY - timedelta(days=7), 1, "2026-11-20 09:00:00"),
            ]
            for chore, user, week, done, at in trash:
                await conn.execute(
                    "INSERT INTO trash_assignments (chore_id, user_id, week_start, is_completed, completed_at)"
                    " VALUES (?, ?, ?, ?, ?);",
                    (chore, user, week.isoformat(), done, at),
                )
            await conn.commit()

    run(seed())
    return path


def text():
    history = run(DatabaseManager.get_user_history(TG_ID))
    return "\n".join(format_user_history("Miguel", history, TODAY, "Europe/Rome"))


def test_history_only_own_most_recent_first(db):
    history = run(DatabaseManager.get_user_history(TG_ID))
    assert len(history["shifts"]) == 4 and len(history["trash"]) == 3
    days = [s["day"] for s in history["shifts"]]
    assert days == sorted(days, reverse=True)


def test_done_shows_completion_date(db):
    t = text()
    assert "`BAGNO1` — fatto il 10/11/2026" in t


def test_completion_date_uses_local_timezone(db):
    # 23:30 UTC del 4/11 sono le 00:30 del 5/11 in Italia
    assert "`CUCINA` — recuperato il 05/11/2026" in text()


def test_missed_and_pending_show_scheduled_date(db):
    t = text()
    assert "`BAGNO2` — non fatto (previsto 16/11/2026)" in t
    assert "`CORRIDOIO` — in attesa (previsto 25/11/2026)" in t


def test_trash_section_with_dates_and_status(db):
    t = text()
    assert "🍾 Butta il vetro dioporco — fatto il 22/11/2026" in t
    assert "🧴 Butta la plastica diomerda — non fatto (settimana del 09/11/2026)" in t
    assert "📰 Butta la carta suino — in attesa (settimana del 23/11/2026)" in t


def test_totals_and_other_users_excluded(db):
    t = text()
    assert "TURNI* _2 ✅ / 1 ❌ / 1 🕒_" in t
    assert "KOSETTINE SETTIMANINE* _1 ✅ / 1 ❌ / 1 🕒_" in t
    assert "20/11/2026" not in t and "17/11/2026" not in t


def test_empty_history_and_long_history_split():
    empty = format_user_history("X", {"shifts": [], "trash": []}, TODAY, "Europe/Rome")
    assert len(empty) == 1 and "Nessun turno ancora" in empty[0] and "Nessuna Kosettina ancora" in empty[0]

    many = [{"name": "cucina", "day": "2026-01-05", "is_completed": 1,
             "completed_at": "2026-01-05 10:00:00", "recovered": 0}] * 400
    chunks = format_user_history("X", {"shifts": many, "trash": []}, TODAY, "Europe/Rome")
    assert len(chunks) > 1 and all(len(c) <= 4096 for c in chunks)


def _upd(user_id):
    upd = MagicMock()
    upd.effective_user.id = user_id
    upd.message.reply_text = AsyncMock()
    return upd


def test_command_replies_with_history_or_asks_registration(db):
    upd = _upd(TG_ID)
    run(sh.history_command(upd, MagicMock()))
    assert "STORICO DI MIGUEL DE SEGANTES" in upd.message.reply_text.call_args.args[0]

    stranger = _upd(999)
    run(sh.history_command(stranger, MagicMock()))
    assert "registrato" in stranger.message.reply_text.call_args.args[0]
