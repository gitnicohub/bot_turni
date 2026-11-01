import asyncio
from datetime import date, timedelta

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
from database.db_manager import DatabaseManager
from utils.helpers import format_weekly_report

TODAY = date(2026, 11, 1)
MONDAY = date(2026, 10, 26)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "stats.db")
    monkeypatch.setattr(dbm, "DATABASE_PATH", path)
    monkeypatch.setattr(dbs, "DATABASE_PATH", path)
    asyncio.run(dbs.init_db())
    return path


def add_shifts(path, rows):
    """rows: (task_id, user_id, scheduled_date, is_completed)"""
    async def go():
        async with aiosqlite.connect(path) as conn:
            for task_id, user_id, d, done in rows:
                await conn.execute(
                    "INSERT INTO shifts (task_id, user_id, scheduled_date, is_completed) VALUES (?, ?, ?, ?);",
                    (task_id, user_id, d.isoformat(), done),
                )
            await conn.commit()
    asyncio.run(go())


def stats(today=TODAY):
    return {r["user_name"]: r for r in asyncio.run(DatabaseManager.get_all_time_stats(today))}


def test_unfinished_shift_stays_pending_until_the_week_ends(db):
    # utente 1: un completato, uno di due settimane fa non fatto, uno di sabato scorso e uno di oggi non fatti
    add_shifts(db, [
        (1, 1, MONDAY, 1),
        (2, 1, MONDAY - timedelta(days=7), 0),
        (3, 1, TODAY - timedelta(days=1), 0),
        (4, 1, TODAY, 0),
    ])
    r = stats()["Miguel de Segantes"]
    assert (r["completed"], r["missed"], r["pending"]) == (1, 1, 2)


def test_pending_shifts_become_missed_when_the_week_expires(db):
    add_shifts(db, [
        (1, 1, MONDAY + timedelta(days=1), 0),  # martedì della settimana in corso
        (2, 1, TODAY, 0),                       # domenica
    ])
    sunday = stats(TODAY)["Miguel de Segantes"]
    assert (sunday["missed"], sunday["pending"]) == (0, 2)
    monday_after = stats(TODAY + timedelta(days=1))["Miguel de Segantes"]
    assert (monday_after["missed"], monday_after["pending"]) == (2, 0)


def test_shift_moved_within_week_is_still_pending_not_missed(db):
    add_shifts(db, [(1, 1, MONDAY + timedelta(days=5), 0)])  # spostato a sabato
    r = stats(MONDAY + timedelta(days=3))["Miguel de Segantes"]  # giovedì
    assert (r["missed"], r["pending"]) == (0, 1)


def test_future_unfinished_shift_is_pending(db):
    add_shifts(db, [(1, 2, TODAY + timedelta(days=3), 0)])
    r = stats()["Giorgio Masturbo"]
    assert (r["completed"], r["missed"], r["pending"]) == (0, 0, 1)


def test_completed_shift_today_is_not_pending(db):
    add_shifts(db, [(1, 3, TODAY, 1)])
    r = stats()["Giuseppe Pio Stigmate"]
    assert (r["completed"], r["missed"], r["pending"]) == (1, 0, 0)


def test_totals_are_equal_for_everyone_with_same_number_of_shifts(db):
    """Il bug: chi aveva un turno di oggi non completato risultava con un turno in meno."""
    rows = []
    for user_id in range(1, 6):
        rows.append((user_id, user_id, MONDAY - timedelta(days=14), 1))
        rows.append((user_id, user_id, MONDAY - timedelta(days=7), 0))  # settimana scaduta: mancato
        # due utenti hanno il turno spostato a oggi e non ancora fatto
        rows.append((user_id, user_id, TODAY if user_id in (1, 5) else MONDAY, 0 if user_id in (1, 5) else 1))
    add_shifts(db, rows)
    totals = {n: r["completed"] + r["missed"] + r["pending"] for n, r in stats().items()}
    assert set(totals.values()) == {3}


def test_report_shows_pending_only_when_present():
    ranking = [
        {"user_name": "Miguel", "completed": 4, "missed": 2, "pending": 1},
        {"user_name": "Giorgio", "completed": 4, "missed": 3, "pending": 0},
    ]
    text = format_weekly_report(MONDAY, [], ranking)
    assert "Miguel* — 4 ✅ / 2 ❌ / 1 🕒" in text
    assert "Giorgio* — 4 ✅ / 3 ❌" in text
    assert "Giorgio* — 4 ✅ / 3 ❌ /" not in text
    assert "in attesa 🕒" in text


def test_report_handles_ranking_without_pending_key():
    text = format_weekly_report(MONDAY, [], [{"user_name": "Miguel", "completed": 1, "missed": 0}])
    assert "Miguel* — 1 ✅ / 0 ❌" in text
