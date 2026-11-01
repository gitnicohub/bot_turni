import asyncio
import random
from collections import Counter
from datetime import date, timedelta

import aiosqlite
import pytest

import database.db_manager as dbm
import database.db_setup as dbs
from database.assignment import compute_week_assignments
from database.db_manager import DatabaseManager

START = date(2026, 9, 14)  # lunedì
TASKS = [1, 2, 3, 4, 5]
USERS = [1, 2, 3, 4, 5]


def simulate(weeks, tasks=TASKS, users=USERS, seed=0, history=None):
    """Genera `weeks` settimane consecutive e restituisce lo storico completo."""
    rng = random.Random(seed)
    history = list(history or [])
    first = START + timedelta(days=7 * len({d - timedelta(days=d.weekday()) for _, _, d in history}))
    for w in range(weeks):
        monday = first + timedelta(days=7 * w)
        for task_id, user_id, d in compute_week_assignments(
            monday, tasks, users, history=history, rng=rng
        ):
            history.append((task_id, user_id, d))
    return history


def by_week(history):
    weeks = {}
    for task_id, user_id, d in history:
        weeks.setdefault(d - timedelta(days=d.weekday()), {})[task_id] = user_id
    return [weeks[k] for k in sorted(weeks)]


@pytest.mark.parametrize("seed", range(20))
def test_everyone_gets_exactly_one_task_each_week(seed):
    for week in by_week(simulate(30, seed=seed)):
        assert sorted(week) == TASKS
        assert sorted(week.values()) == USERS


@pytest.mark.parametrize("seed", range(20))
def test_never_same_task_two_weeks_in_a_row(seed):
    weeks = by_week(simulate(60, seed=seed))
    for prev, cur in zip(weeks, weeks[1:]):
        assert all(prev[t] != cur[t] for t in TASKS)


@pytest.mark.parametrize("seed", range(20))
def test_long_run_is_balanced(seed):
    """Dopo 50 settimane (10 giri) ogni persona ha fatto ogni compito 10 volte, al massimo ±1."""
    counts = Counter((u, t) for t, u, _ in simulate(50, seed=seed))
    assert max(counts.values()) - min(counts.values()) <= 1


@pytest.mark.parametrize("seed", range(20))
def test_every_full_cycle_covers_all_tasks(seed):
    """In ogni blocco di 5 settimane nessuno fa lo stesso compito due volte."""
    weeks = by_week(simulate(50, seed=seed))
    for i in range(0, 50, 5):
        block = weeks[i:i + 5]
        for user in USERS:
            done = [t for week in block for t, u in week.items() if u == user]
            assert len(set(done)) == 5, (seed, i, user, done)


def test_assignment_is_not_predictable():
    outcomes = {tuple(sorted(by_week(simulate(1, seed=s))[0].items())) for s in range(30)}
    assert len(outcomes) > 10


def test_ignores_history_from_the_future_and_same_week():
    monday = START + timedelta(days=14)
    future = [(1, 1, monday), (2, 2, monday + timedelta(days=30))]
    with_future = compute_week_assignments(monday, TASKS, USERS, history=future, rng=random.Random(5))
    without = compute_week_assignments(monday, TASKS, USERS, history=[], rng=random.Random(5))
    assert with_future == without


def test_task_days_follow_fixed_order_even_for_subset():
    monday = START
    result = compute_week_assignments(monday, [3, 5], USERS, all_task_ids=TASKS, rng=random.Random(1))
    days = {t: d for t, _, d in result}
    assert days == {3: monday + timedelta(days=2), 5: monday + timedelta(days=4)}


def test_subset_avoids_users_already_busy_this_week():
    busy = {1: 1, 2: 2, 3: 3}  # utenti 1,2,3 hanno già un compito in settimana
    for seed in range(30):
        result = compute_week_assignments(
            START, [4, 5], USERS, all_task_ids=TASKS, already_assigned=busy, rng=random.Random(seed)
        )
        assert {u for _, u, _ in result} == {4, 5}


def test_more_tasks_than_users_spreads_load():
    tasks = list(range(1, 8))  # 7 compiti, 5 persone
    for seed in range(20):
        result = compute_week_assignments(START, tasks, USERS, rng=random.Random(seed))
        load = Counter(u for _, u, _ in result)
        assert set(load) == set(USERS)  # tutti ne hanno almeno uno
        assert max(load.values()) <= 2


def test_large_group_stays_valid_and_fast():
    users = list(range(1, 13))
    tasks = list(range(1, 8))  # 7 compiti (uno per giorno), 12 persone
    weeks = by_week(simulate(30, tasks=tasks, users=users, seed=3))
    for week in weeks:
        assert len(set(week.values())) == 7  # nessuno ha due compiti
    for prev, cur in zip(weeks, weeks[1:]):
        assert all(prev[t] != cur[t] for t in tasks)


def test_square_group_of_twelve_gives_one_task_each():
    users = tasks = list(range(1, 13))
    result = compute_week_assignments(START, tasks, users, rng=random.Random(1))
    assert sorted(u for _, u, _ in result) == users


# Storico reale della VM (task: 1 bagno1, 2 bagno2, 3 cucina, 4 corridoio, 5 infrasettimanale;
# utenti: 1 Miguel, 2 Giorgio, 3 Giuseppe, 4 Cristiana, 5 Giovanna) fino alla settimana del 26/10.
REAL = [
    (1, 3, "2026-09-14"), (2, 1, "2026-09-15"), (3, 5, "2026-09-16"), (4, 4, "2026-09-17"), (5, 2, "2026-09-18"),
    (3, 4, "2026-09-23"), (1, 2, "2026-09-25"), (2, 3, "2026-09-25"), (4, 1, "2026-09-26"), (5, 5, "2026-09-26"),
    (2, 4, "2026-09-30"), (3, 5, "2026-09-30"), (1, 3, "2026-10-02"), (4, 2, "2026-10-02"), (5, 1, "2026-10-03"),
    (1, 2, "2026-10-05"), (2, 3, "2026-10-07"), (5, 4, "2026-10-09"), (3, 1, "2026-10-10"), (4, 5, "2026-10-10"),
    (2, 4, "2026-10-13"), (3, 5, "2026-10-14"), (1, 1, "2026-10-15"), (4, 2, "2026-10-15"), (5, 3, "2026-10-16"),
    (1, 4, "2026-10-19"), (2, 5, "2026-10-20"), (5, 2, "2026-10-23"), (4, 1, "2026-10-24"), (3, 3, "2026-10-25"),
    (2, 2, "2026-10-27"), (3, 5, "2026-11-01"), (4, 4, "2026-10-29"), (1, 3, "2026-10-30"), (5, 1, "2026-11-01"),
]
REAL = [(t, u, date.fromisoformat(d)) for t, u, d in REAL]
NEXT_MONDAY = date(2026, 11, 2)


def test_real_history_next_week():
    """Con lo storico reale l'unico ottimo è dare a ognuno un compito mai fatto (o fatto una volta sola)."""
    last_week = {t: u for t, u, d in REAL if date(2026, 10, 26) <= d <= date(2026, 11, 1)}
    counts = Counter((u, t) for t, u, _ in REAL)
    for seed in range(200):
        result = compute_week_assignments(NEXT_MONDAY, TASKS, USERS, history=REAL, rng=random.Random(seed))
        picked = {t: u for t, u, _ in result}
        assert sorted(picked.values()) == USERS
        # nessuno rifà il compito della settimana scorsa
        assert all(last_week[t] != picked[t] for t in TASKS)
        # nessuno riceve un compito già fatto 2+ volte, perché esiste sempre un'alternativa
        assert all(counts[(u, t)] < 2 for t, u in picked.items())
        # bagno1 a Giovanna (0 volte), cucina a Giorgio (0), corridoio a Giuseppe (0)
        assert (picked[1], picked[3], picked[4]) == (5, 2, 3)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    monkeypatch.setattr(dbm, "DATABASE_PATH", path)
    monkeypatch.setattr(dbs, "DATABASE_PATH", path)
    asyncio.run(dbs.init_db())
    return path


def test_ensure_week_shifts_over_many_weeks(db):
    async def go():
        for w in range(25):
            await DatabaseManager.ensure_week_shifts(START + timedelta(days=7 * w))
        async with aiosqlite.connect(db) as conn:
            async with conn.execute("SELECT task_id, user_id, scheduled_date FROM shifts") as cur:
                return [(t, u, date.fromisoformat(d)) for t, u, d in await cur.fetchall()]

    history = asyncio.run(go())
    weeks = by_week(history)
    assert len(weeks) == 25
    for week in weeks:
        assert sorted(week.values()) == USERS
    for prev, cur in zip(weeks, weeks[1:]):
        assert all(prev[t] != cur[t] for t in TASKS)
    counts = Counter((u, t) for t, u, _ in history)
    assert max(counts.values()) - min(counts.values()) <= 1


def test_ensure_week_shifts_is_idempotent_and_keeps_moved_shift(db):
    async def go():
        await DatabaseManager.ensure_week_shifts(START)
        before = await DatabaseManager.get_shifts_for_week(START)
        await DatabaseManager.reschedule_shift(before[0]["shift_id"], START + timedelta(days=5), START)
        await DatabaseManager.ensure_week_shifts(START)
        return before, await DatabaseManager.get_shifts_for_week(START)

    before, after = asyncio.run(go())
    assert len(after) == len(before) == 5
