import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
from database.db_manager import DatabaseManager
from handlers import callback_handler
from handlers.callback_handler import build_recover_keyboard, recover_callback
import handlers.shifts_handler as sh
from handlers.shifts_handler import recover_command

MONDAY = date(2026, 11, 2)  # lunedì della settimana corrente
LAST_WEEK = MONDAY - timedelta(days=7)
TWO_WEEKS_AGO = MONDAY - timedelta(days=14)
TG_ID = 111
OTHER_TG_ID = 222


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(callback_handler, "_today", lambda: MONDAY)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(dbm, "DATABASE_PATH", path)
    monkeypatch.setattr(dbs, "DATABASE_PATH", path)
    run(dbs.init_db())

    async def seed():
        async with aiosqlite.connect(path) as conn:
            await conn.execute("UPDATE users SET telegram_id = ? WHERE id = 1;", (TG_ID,))
            await conn.execute("UPDATE users SET telegram_id = ? WHERE id = 2;", (OTHER_TG_ID,))
            rows = [
                (1, 1, TWO_WEEKS_AGO, 0),   # id 1: utente 1, mancato
                (2, 1, LAST_WEEK, 0),       # id 2: utente 1, mancato
                (3, 1, MONDAY, 0),          # id 3: utente 1, settimana corrente (non recuperabile)
                (4, 2, LAST_WEEK, 0),       # id 4: utente 2, mancato (non di utente 1)
                (1, 1, LAST_WEEK - timedelta(days=14), 1),  # id 5: utente 1, già fatto
            ]
            for task, user, day, done in rows:
                await conn.execute(
                    "INSERT INTO shifts (task_id, user_id, scheduled_date, is_completed) VALUES (?, ?, ?, ?);",
                    (task, user, day.isoformat(), done),
                )
            await conn.commit()

    run(seed())
    return path


def shift(shift_id):
    return run(DatabaseManager.get_shift(shift_id))


def test_missed_shifts_only_own_past_uncompleted(db):
    missed = run(DatabaseManager.get_missed_shifts_for_user(TG_ID, MONDAY))
    assert [s["shift_id"] for s in missed] == [1, 2]  # dal più vecchio, senza id 3/4/5


def test_week_still_running_is_not_missed(db):
    # a domenica la settimana corrente è ancora in corso: id 3 non è recuperabile
    sunday = MONDAY + timedelta(days=6)
    missed = run(DatabaseManager.get_missed_shifts_for_user(TG_ID, sunday))
    assert 3 not in [s["shift_id"] for s in missed]
    # dal lunedì dopo lo diventa
    missed = run(DatabaseManager.get_missed_shifts_for_user(TG_ID, MONDAY + timedelta(days=7)))
    assert 3 in [s["shift_id"] for s in missed]


def test_recover_marks_done_and_updates_stats(db):
    before = {r["user_name"]: r for r in run(DatabaseManager.get_all_time_stats(MONDAY))}
    name = shift(2)["user_name"]

    assert run(DatabaseManager.recover_shift(2, TG_ID, MONDAY)) is True
    s = shift(2)
    assert s["is_completed"] == 1

    after = {r["user_name"]: r for r in run(DatabaseManager.get_all_time_stats(MONDAY))}
    assert after[name]["completed"] == before[name]["completed"] + 1
    assert after[name]["missed"] == before[name]["missed"] - 1
    assert 2 not in [x["shift_id"] for x in run(DatabaseManager.get_missed_shifts_for_user(TG_ID, MONDAY))]


def test_recover_rejects_current_week_other_user_and_done(db):
    assert run(DatabaseManager.recover_shift(3, TG_ID, MONDAY)) is False  # settimana corrente
    assert run(DatabaseManager.recover_shift(4, TG_ID, MONDAY)) is False  # turno di un altro
    assert run(DatabaseManager.recover_shift(5, TG_ID, MONDAY)) is False  # già fatto
    assert run(DatabaseManager.recover_shift(999, TG_ID, MONDAY)) is False
    assert shift(3)["is_completed"] == 0 and shift(4)["is_completed"] == 0


def test_recover_twice_fails(db):
    assert run(DatabaseManager.recover_shift(1, TG_ID, MONDAY)) is True
    assert run(DatabaseManager.recover_shift(1, TG_ID, MONDAY)) is False


def test_undo_clears_recovered_flag(db):
    run(DatabaseManager.recover_shift(1, TG_ID, MONDAY))
    assert run(DatabaseManager.mark_shift_uncompleted(1, TG_ID)) is True

    async def flag():
        async with aiosqlite.connect(dbm.DATABASE_PATH) as conn:
            async with conn.execute("SELECT recovered, is_completed FROM shifts WHERE id = 1;") as c:
                return await c.fetchone()

    assert run(flag()) == (0, 0)


def test_keyboard_has_button_per_shift_plus_cancel(db):
    missed = run(DatabaseManager.get_missed_shifts_for_user(TG_ID, MONDAY))
    kb = build_recover_keyboard(missed)
    assert [row[0].callback_data for row in kb.inline_keyboard] == ["recover:1", "recover:2", "recover:skip"]


def _update(data, user_id=TG_ID):
    update = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.effective_user.id = user_id
    return update


def _context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def test_callback_recovers_and_broadcasts_to_everyone(db):
    ctx = _context()
    upd = _update("recover:2")
    run(recover_callback(upd, ctx))

    assert shift(2)["is_completed"] == 1
    assert "recuperato" in upd.callback_query.edit_message_text.call_args.args[0]

    sent = {c.kwargs["chat_id"]: c.kwargs["text"] for c in ctx.bot.send_message.call_args_list}
    assert set(sent) == {TG_ID, OTHER_TG_ID}
    name, task = shift(2)["user_name"], shift(2)["task_name"]
    expected = f"*{name}* ha recuperato il turno *{task}* del *{LAST_WEEK.strftime('%d/%m/%Y')}*"
    assert all(expected in text for text in sent.values())


def test_callback_rejects_foreign_shift_without_broadcast(db):
    ctx = _context()
    upd = _update("recover:4")
    run(recover_callback(upd, ctx))

    assert shift(4)["is_completed"] == 0
    assert "Impossibile" in upd.callback_query.edit_message_text.call_args.args[0]
    ctx.bot.send_message.assert_not_called()


def test_callback_double_click_broadcasts_once(db):
    ctx = _context()
    run(recover_callback(_update("recover:1"), ctx))
    n = ctx.bot.send_message.call_count
    run(recover_callback(_update("recover:1"), ctx))
    assert ctx.bot.send_message.call_count == n


def test_callback_skip_changes_nothing(db):
    ctx = _context()
    run(recover_callback(_update("recover:skip"), ctx))
    assert shift(1)["is_completed"] == 0
    ctx.bot.send_message.assert_not_called()


def _message_update(user_id=TG_ID):
    upd = MagicMock()
    upd.effective_user.id = user_id
    upd.message.reply_text = AsyncMock()
    return upd


def test_recupera_command_lists_missed_shifts(db, monkeypatch):
    monkeypatch.setattr(sh, "datetime", MagicMock(now=lambda tz: MagicMock(date=lambda: MONDAY)))
    upd = _message_update()
    run(recover_command(upd, _context()))
    kb = upd.message.reply_text.call_args.kwargs["reply_markup"]
    assert [row[0].callback_data for row in kb.inline_keyboard] == ["recover:1", "recover:2", "recover:skip"]


def test_recupera_command_nothing_to_recover(db, monkeypatch):
    monkeypatch.setattr(sh, "datetime", MagicMock(now=lambda tz: MagicMock(date=lambda: MONDAY)))
    run(DatabaseManager.recover_shift(1, TG_ID, MONDAY))
    run(DatabaseManager.recover_shift(2, TG_ID, MONDAY))
    upd = _message_update()
    run(recover_command(upd, _context()))
    assert "in regola" in upd.message.reply_text.call_args.args[0]


def test_recupera_command_unregistered_user(db):
    upd = _message_update(user_id=999)
    run(recover_command(upd, _context()))
    assert "Non risulti ancora registrato" in upd.message.reply_text.call_args.args[0]


def test_report_shows_recovered_shift_as_done(db):
    from utils.helpers import format_weekly_report
    run(DatabaseManager.recover_shift(2, TG_ID, MONDAY))
    week = run(DatabaseManager.get_shifts_for_week(LAST_WEEK))
    ranking = run(DatabaseManager.get_all_time_stats(MONDAY))
    text = format_weekly_report(LAST_WEEK, week, ranking)
    mine = [s for s in week if s["shift_id"] == 2][0]
    assert mine["is_completed"] == 1
    assert "✅ Completato" in text
