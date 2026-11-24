import asyncio
import datetime
from collections import Counter
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
import handlers.callback_handler as ch
import handlers.shifts_handler as sh
import scheduler.scheduler_jobs as jobs
from config import TRASH_CHORES
from database.db_manager import DatabaseManager
from utils.helpers import format_trash_list, format_weekly_report

START = date(2026, 11, 23)  # lunedì
TG_IDS = {1: 111, 2: 222}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "trash.db")
    monkeypatch.setattr(dbm, "DATABASE_PATH", path)
    monkeypatch.setattr(dbs, "DATABASE_PATH", path)
    run(dbs.init_db())

    async def seed():
        async with aiosqlite.connect(path) as conn:
            for uid, tg in TG_IDS.items():
                await conn.execute("UPDATE users SET telegram_id = ? WHERE id = ?;", (tg, uid))
            await conn.commit()

    run(seed())
    return path


def history_rows(path):
    async def go():
        async with aiosqlite.connect(path) as conn:
            async with conn.execute(
                "SELECT week_start, chore_id, user_id FROM trash_assignments ORDER BY week_start, chore_id;"
            ) as c:
                return await c.fetchall()
    return run(go())


def generate(weeks):
    async def go():
        for w in range(weeks):
            await DatabaseManager.ensure_week_trash(START + timedelta(days=7 * w))
    run(go())


# ---------- lista e assegnazione ----------

def test_chores_are_seeded_verbatim_in_order(db):
    names = [c["name"] for c in run(DatabaseManager.get_trash_chores())]
    assert names == [
        "Butta il vetro dioporco",
        "Butta la plastica diomerda",
        "Butta la carta suino",
        "Butta l'indifferenziata pezzo di merda",
        "Butta l'organico ca ste puzz d merd",
    ]


def test_each_week_everyone_gets_exactly_one_chore(db):
    generate(30)
    by_week = {}
    for week, chore, user in history_rows(db):
        by_week.setdefault(week, []).append((chore, user))
    assert len(by_week) == 30
    for rows in by_week.values():
        assert sorted(c for c, _ in rows) == [1, 2, 3, 4, 5]
        assert sorted(u for _, u in rows) == [1, 2, 3, 4, 5]


def test_never_same_chore_in_consecutive_weeks(db):
    generate(100)
    last = {}
    for week, chore, user in history_rows(db):
        week_date = date.fromisoformat(week)
        prev = last.get(user)
        if prev and (week_date - prev[0]).days == 7:
            assert prev[1] != chore, f"utente {user} ha {chore} due settimane di fila ({week})"
        last[user] = (week_date, chore)


def test_rotation_is_perfectly_balanced(db):
    generate(100)
    counts = Counter()
    seen_at = {}
    for week, chore, user in history_rows(db):
        counts[(user, chore)] += 1
        seen_at.setdefault(week, None)
        # a ogni settimana nessuno è mai in vantaggio di più di 1 su un compito
        for u in range(1, 6):
            per_chore = [counts[(u, c)] for c in range(1, 6)]
            assert max(per_chore) - min(per_chore) <= 1
    # dopo 100 settimane (20 giri) ognuno ha fatto ogni compito esattamente 20 volte
    assert all(counts[(u, c)] == 20 for u in range(1, 6) for c in range(1, 6))


def test_first_five_weeks_cover_every_chore_once_per_person(db):
    generate(5)
    counts = Counter((u, c) for _, c, u in history_rows(db))
    assert all(counts[(u, c)] == 1 for u in range(1, 6) for c in range(1, 6))


def test_ensure_week_trash_is_idempotent(db):
    assert run(DatabaseManager.ensure_week_trash(START)) is True
    before = history_rows(db)
    assert run(DatabaseManager.ensure_week_trash(START)) is False
    assert history_rows(db) == before


# ---------- messaggio ----------

def test_list_message_is_numbered_titled_and_uses_the_exact_texts(db):
    run(DatabaseManager.ensure_week_trash(START))
    text = format_trash_list(run(DatabaseManager.get_trash_for_week(START)))
    assert "KOSETTINE SETTIMANINE" in text
    for i, (name, emoji) in enumerate(TRASH_CHORES):
        assert name in text and emoji in text
    positions = [text.index(name) for name, _ in TRASH_CHORES]
    assert positions == sorted(positions)
    assert "1️⃣" in text and "5️⃣" in text
    assert text.count("In attesa") == 5


# ---------- /fattoimmondizia e callback ----------

def _msg_update(user_id):
    upd = MagicMock()
    upd.effective_user.id = user_id
    upd.message.reply_text = AsyncMock()
    return upd


@pytest.fixture
def fixed_week(monkeypatch):
    monkeypatch.setattr(sh, "_current_monday", lambda: START)
    monkeypatch.setattr(ch, "_today", lambda: START)


def _assigned_to(tg):
    return [t for t in run(DatabaseManager.get_trash_for_week(START)) if t["telegram_id"] == tg]


def test_fattoimmondizia_marks_done_and_is_idempotent(db, fixed_week):
    upd = _msg_update(111)
    run(sh.trash_done_command(upd, _ctx()))
    assert "Segnato come fatto" in upd.message.reply_text.call_args.args[0]
    assert all(t["is_completed"] for t in _assigned_to(111))
    assert not any(t["is_completed"] for t in _assigned_to(222))

    upd2 = _msg_update(111)
    run(sh.trash_done_command(upd2, _ctx()))
    assert "già fatto" in upd2.message.reply_text.call_args.args[0]


def test_fattoimmondizia_requires_registration(db, fixed_week):
    upd = _msg_update(999)
    run(sh.trash_done_command(upd, _ctx()))
    assert "registrato" in upd.message.reply_text.call_args.args[0]


def _cb_update(data, user_id):
    upd = MagicMock()
    upd.callback_query.data = data
    upd.callback_query.answer = AsyncMock()
    upd.callback_query.edit_message_text = AsyncMock()
    upd.effective_user.id = user_id
    return upd


def test_callback_done_fail_and_foreign(db, fixed_week):
    run(DatabaseManager.ensure_week_trash(START))
    mine = _assigned_to(111)[0]["assignment_id"]

    foreign = _cb_update(f"trash:{mine}:done", 222)
    run(ch.trash_callback(foreign, MagicMock()))
    assert "non ti risulta" in foreign.callback_query.edit_message_text.call_args.args[0]
    assert not _assigned_to(111)[0]["is_completed"]

    fail = _cb_update(f"trash:{mine}:fail", 111)
    run(ch.trash_callback(fail, MagicMock()))
    assert not _assigned_to(111)[0]["is_completed"]

    done = _cb_update(f"trash:{mine}:done", 111)
    run(ch.trash_callback(done, MagicMock()))
    assert _assigned_to(111)[0]["is_completed"]

    again = _cb_update(f"trash:{mine}:done", 111)
    run(ch.trash_callback(again, MagicMock()))
    assert "già" in again.callback_query.edit_message_text.call_args.args[0]


# ---------- job ----------

class FakeDateTime(datetime.datetime):
    fixed = None

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def _ctx():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def test_monday_job_generates_and_sends_list_to_all_registered(db, monkeypatch):
    FakeDateTime.fixed = datetime.datetime(2026, 11, 23, 7, 0)
    monkeypatch.setattr(jobs.datetime, "datetime", FakeDateTime)
    ctx = _ctx()
    run(jobs.generate_weekly_shifts_job(ctx))

    assert len(run(DatabaseManager.get_trash_for_week(START))) == 5
    sent = {c.kwargs["chat_id"]: c.kwargs["text"] for c in ctx.bot.send_message.call_args_list}
    assert set(sent) == set(TG_IDS.values())
    assert all("KOSETTINE SETTIMANINE" in t for t in sent.values())


def test_sunday_job_asks_only_pending_registered_users(db, monkeypatch):
    run(DatabaseManager.ensure_week_trash(START))
    run(DatabaseManager.complete_trash_for_user(222, START))  # utente 222 ha già fatto
    FakeDateTime.fixed = datetime.datetime(2026, 11, 29, 23, 0)
    monkeypatch.setattr(jobs.datetime, "datetime", FakeDateTime)
    ctx = _ctx()
    run(jobs.sunday_trash_verification_job(ctx))

    chats = [c.kwargs["chat_id"] for c in ctx.bot.send_message.call_args_list]
    assert chats == [111]  # i non registrati non ricevono nulla, chi ha fatto nemmeno
    kb = ctx.bot.send_message.call_args.kwargs["reply_markup"]
    assert [b.callback_data.split(":")[2] for b in kb.inline_keyboard[0]] == ["done", "fail"]


def test_sunday_job_is_scheduled_on_sunday_23(db):
    jq = MagicMock()
    jobs.setup_scheduled_jobs(jq)
    calls = {c.kwargs["name"]: c.kwargs for c in jq.run_daily.call_args_list}
    assert calls["sunday_trash_verification"]["days"] == (0,)
    assert calls["sunday_trash_verification"]["time"].hour == 23


# ---------- statistiche e report ----------

def test_trash_stats_pending_then_missed_after_week_ends(db):
    run(DatabaseManager.ensure_week_trash(START))
    run(DatabaseManager.complete_trash_for_user(111, START))
    sunday = START + timedelta(days=6)
    stats = {r["user_name"]: r for r in run(DatabaseManager.get_trash_stats(sunday))}
    u1 = stats["Miguel de Segantes"]
    assert (u1["completed"], u1["missed"], u1["pending"]) == (1, 0, 0)
    u3 = stats["Giuseppe Pio Stigmate"]
    assert (u3["completed"], u3["missed"], u3["pending"]) == (0, 0, 1)

    monday_after = START + timedelta(days=7)
    stats = {r["user_name"]: r for r in run(DatabaseManager.get_trash_stats(monday_after))}
    u3 = stats["Giuseppe Pio Stigmate"]
    assert (u3["completed"], u3["missed"], u3["pending"]) == (0, 1, 0)


def test_report_includes_trash_outcome_and_ranking(db):
    run(DatabaseManager.ensure_week_trash(START))
    run(DatabaseManager.complete_trash_for_user(111, START))
    monday_after = START + timedelta(days=7)
    trash = run(DatabaseManager.get_trash_for_week(START))
    ranking = run(DatabaseManager.get_trash_stats(monday_after))
    text = format_weekly_report(START, [], [], trash, ranking)

    assert "KOSETTINE SETTIMANINE" in text
    assert "✅ Fatto" in text and "❌ Non fatto" in text
    assert "CLASSIFICA KOSETTINE" in text


def test_report_without_trash_is_unchanged():
    text = format_weekly_report(START, [], [])
    assert "KOSETTINE" not in text


def test_previous_week_report_end_to_end(db):
    run(DatabaseManager.ensure_week_trash(START))
    text = run(jobs.build_previous_week_report(START + timedelta(days=7)))
    assert "KOSETTINE" in text


# ---------- broadcast al completamento ----------

def _broadcasts(ctx):
    return {c.kwargs["chat_id"]: c.kwargs["text"] for c in ctx.bot.send_message.call_args_list}


def test_fattoimmondizia_broadcasts_to_everyone(db, fixed_week):
    ctx = _ctx()
    run(sh.trash_done_command(_msg_update(111), ctx))
    chore = _assigned_to(111)[0]["chore_name"]
    sent = _broadcasts(ctx)
    assert set(sent) == set(TG_IDS.values())
    expected = f"*Miguel de Segantes* ha buttato {chore.removeprefix('Butta ')}, comblimend strunz!!!!"
    assert all(expected in t for t in sent.values())

    ctx2 = _ctx()  # secondo invio: già fatto, nessun broadcast
    run(sh.trash_done_command(_msg_update(111), ctx2))
    ctx2.bot.send_message.assert_not_called()


def test_callback_done_broadcasts_once_fail_never(db, fixed_week):
    run(DatabaseManager.ensure_week_trash(START))
    aid = _assigned_to(111)[0]["assignment_id"]

    ctx = _ctx()
    run(ch.trash_callback(_cb_update(f"trash:{aid}:fail", 111), ctx))
    ctx.bot.send_message.assert_not_called()

    run(ch.trash_callback(_cb_update(f"trash:{aid}:done", 111), ctx))
    assert set(_broadcasts(ctx)) == set(TG_IDS.values())
    n = ctx.bot.send_message.call_count
    run(ch.trash_callback(_cb_update(f"trash:{aid}:done", 111), ctx))
    assert ctx.bot.send_message.call_count == n
