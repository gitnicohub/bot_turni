from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite

from database.db_manager import DatabaseManager
from handlers.callback_handler import verify_callback
from tests.test_recover import MONDAY, TG_ID, OTHER_TG_ID, db, fixed_today, run, shift  # noqa: F401


def _ctx():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _upd(data, user_id=TG_ID):
    upd = MagicMock()
    upd.callback_query.data = data
    upd.callback_query.answer = AsyncMock()
    upd.callback_query.edit_message_text = AsyncMock()
    upd.effective_user.id = user_id
    return upd


def test_done_button_broadcasts_to_everyone(db):
    ctx = _ctx()
    run(verify_callback(_upd("verify:3:done"), ctx))
    assert shift(3)["is_completed"] == 1
    sent = {c.kwargs["chat_id"]: c.kwargs["text"] for c in ctx.bot.send_message.call_args_list}
    assert set(sent) == {TG_ID, OTHER_TG_ID}
    expected = f"*{shift(3)['user_name']}* ha fatto metà del suo dovere facendo il *{shift(3)['task_name']}*"
    assert all(expected in t for t in sent.values())


def test_done_button_twice_broadcasts_once(db):
    ctx = _ctx()
    run(verify_callback(_upd("verify:3:done"), ctx))
    n = ctx.bot.send_message.call_count
    run(verify_callback(_upd("verify:3:done"), ctx))
    assert ctx.bot.send_message.call_count == n
