import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
from database.db_manager import DatabaseManager
from handlers import callback_handler
from handlers.callback_handler import build_reschedule_keyboard, reschedule_callback, verify_callback
from handlers.shifts_handler import reschedule_command

MONDAY = date(2026, 11, 2)  # lunedì
NEXT_MONDAY = MONDAY + timedelta(days=7)
TG_ID = 111


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
            # turno di bagno1 (task 1) lunedì della settimana corrente e della successiva
            await conn.execute("INSERT INTO shifts (task_id, user_id, scheduled_date) VALUES (1, 1, ?);", (MONDAY.isoformat(),))
            await conn.execute("INSERT INTO shifts (task_id, user_id, scheduled_date) VALUES (1, 1, ?);", (NEXT_MONDAY.isoformat(),))
            await conn.commit()

    run(seed())
    return path


def shift_date(shift_id):
    return date.fromisoformat(run(DatabaseManager.get_shift(shift_id))["scheduled_date"])


def test_reschedule_many_times_until_sunday(db):
    for target in [MONDAY + timedelta(days=d) for d in range(1, 7)]:
        assert run(DatabaseManager.reschedule_shift(1, target, MONDAY)) is True
        assert shift_date(1) == target


def test_reschedule_does_not_touch_next_week(db):
    run(DatabaseManager.reschedule_shift(1, MONDAY + timedelta(days=3), MONDAY))
    assert shift_date(2) == NEXT_MONDAY


def test_cannot_leave_current_week(db):
    assert run(DatabaseManager.reschedule_shift(1, NEXT_MONDAY, MONDAY)) is False
    assert shift_date(1) == MONDAY


def test_cannot_move_to_same_day_or_past(db):
    wed = MONDAY + timedelta(days=2)
    run(DatabaseManager.reschedule_shift(1, wed, MONDAY))
    assert run(DatabaseManager.reschedule_shift(1, wed, MONDAY)) is False
    # oggi è mercoledì: lunedì e martedì sono nel passato
    assert run(DatabaseManager.reschedule_shift(1, MONDAY + timedelta(days=1), wed)) is False
    # ma spostare indietro verso un giorno non ancora passato è lecito
    assert run(DatabaseManager.reschedule_shift(1, MONDAY + timedelta(days=1), MONDAY)) is True


def test_cannot_move_completed_shift(db):
    run(DatabaseManager.mark_shift_completed(1, TG_ID))
    assert run(DatabaseManager.reschedule_shift(1, MONDAY + timedelta(days=1), MONDAY)) is False


def test_reschedule_resets_notified(db):
    run(DatabaseManager.mark_notified(1))
    run(DatabaseManager.reschedule_shift(1, MONDAY + timedelta(days=1), MONDAY))
    pending = run(DatabaseManager.get_todays_pending_shifts(MONDAY + timedelta(days=1)))
    assert [s["shift_id"] for s in pending] == [1]


def _days(kb):
    return [row[0].callback_data.split(":")[2] for row in kb.inline_keyboard]


def test_keyboard_offers_today_to_sunday_except_current():
    wed = MONDAY + timedelta(days=2)
    kb = build_reschedule_keyboard(1, wed, today=MONDAY + timedelta(days=1))
    expected = [(MONDAY + timedelta(days=d)).isoformat() for d in (1, 3, 4, 5, 6)]
    assert _days(kb) == expected + ["skip"]


def test_keyboard_none_when_no_day_left():
    sunday = MONDAY + timedelta(days=6)
    assert build_reschedule_keyboard(1, sunday, today=sunday) is None


def _update(data):
    update = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.effective_user.id = TG_ID
    return update


def _context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    ctx.bot.delete_message = AsyncMock()
    ctx.bot.send_photo = AsyncMock()
    ctx.bot.send_voice = AsyncMock()
    return ctx


def test_handler_allows_second_reschedule_and_skip_does_not_block(db):
    tue, wed = MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)
    ctx = _context()

    run(reschedule_callback(_update(f"reschedule:1:{tue.isoformat()}"), ctx))
    assert shift_date(1) == tue

    # "Non spostare" non deve consumare nulla
    run(reschedule_callback(_update("reschedule:1:skip"), ctx))

    upd = _update(f"reschedule:1:{wed.isoformat()}")
    run(reschedule_callback(upd, ctx))
    assert shift_date(1) == wed
    assert "spostato" in upd.callback_query.edit_message_text.call_args.args[0]


def test_fail_after_reschedule_offers_buttons_again(db, monkeypatch):
    monkeypatch.setattr(callback_handler, "pick_random_punishment_image", lambda *_: None)
    monkeypatch.setattr(callback_handler, "pick_random_punishment_audio", lambda *_: None)
    tue = MONDAY + timedelta(days=1)
    monkeypatch.setattr(callback_handler, "_today", lambda: tue)
    run(DatabaseManager.reschedule_shift(1, tue, MONDAY))

    ctx = _context()
    run(verify_callback(_update("verify:1:fail"), ctx))

    kb = ctx.bot.send_message.call_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == f"reschedule:1:{(tue + timedelta(days=1)).isoformat()}"


def test_sposta_command_lists_keyboard_for_open_shift(db, monkeypatch):
    import handlers.shifts_handler as sh
    monkeypatch.setattr(sh, "_current_monday", lambda: MONDAY)
    monkeypatch.setattr(sh.DatabaseManager, "ensure_week_shifts", AsyncMock())
    monkeypatch.setattr(sh, "datetime", MagicMock(now=lambda tz: MagicMock(date=lambda: MONDAY + timedelta(days=1)),
                                                  strptime=__import__("datetime").datetime.strptime))
    upd = MagicMock()
    upd.effective_user.id = TG_ID
    upd.message.reply_text = AsyncMock()
    run(reschedule_command(upd, _context()))

    kb = upd.message.reply_text.call_args.kwargs["reply_markup"]
    # turno di lunedì, oggi martedì: restano mar..dom
    assert _days(kb) == [(MONDAY + timedelta(days=d)).isoformat() for d in range(1, 7)] + ["skip"]


def test_sposta_command_no_open_shifts(db, monkeypatch):
    import handlers.shifts_handler as sh
    monkeypatch.setattr(sh, "_current_monday", lambda: MONDAY)
    monkeypatch.setattr(sh.DatabaseManager, "ensure_week_shifts", AsyncMock())
    run(DatabaseManager.mark_shift_completed(1, TG_ID))
    upd = MagicMock()
    upd.effective_user.id = TG_ID
    upd.message.reply_text = AsyncMock()
    run(reschedule_command(upd, _context()))
    assert "nessun turno o già completato" in upd.message.reply_text.call_args.args[0]
