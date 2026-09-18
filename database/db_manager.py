import aiosqlite
import random
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from config import DATABASE_PATH


MAX_SHUFFLE_ATTEMPTS = 20


def compute_week_assignments(
    monday: date,
    task_ids: List[int],
    user_ids: List[int],
    all_task_ids: Optional[List[int]] = None,
    previous_assignments: Optional[Dict[int, int]] = None,
) -> List[tuple]:
    """Assegna a caso i turni della settimana tra i coinquilini.

    I coinquilini vengono rimescolati (shuffle) e abbinati 1:1 ai turni,
    così l'assegnazione cambia ogni settimana e nessuno si ritrova sempre
    con lo stesso turno. Il turno di un task è programmato su monday + il
    suo indice nell'ordine fisso delle mansioni (Lun..Ven per 5 turni).

    `task_ids` può essere un sottoinsieme (es. solo i task ancora privi di
    turno in settimana): `all_task_ids`, l'elenco completo ordinato, serve
    in quel caso per calcolare comunque il giorno corretto di ciascun task
    tramite il suo indice originale, invece di quello nella lista filtrata.

    `previous_assignments` (task_id -> user_id della settimana precedente),
    se fornito, fa ritentare lo shuffle fino a MAX_SHUFFLE_ATTEMPTS volte
    per evitare che un task ricapiti alla stessa persona due settimane di
    fila. Con pochi coinquilini/task non è sempre possibile evitarlo del
    tutto: è un tentativo best-effort, non una garanzia.
    """
    order_reference = all_task_ids if all_task_ids is not None else task_ids
    day_offset = {tid: i for i, tid in enumerate(order_reference)}
    previous_assignments = previous_assignments or {}
    n = len(user_ids)

    candidate = None
    for _ in range(MAX_SHUFFLE_ATTEMPTS):
        shuffled_users = user_ids.copy()
        random.shuffle(shuffled_users)
        candidate = {
            task_id: shuffled_users[i % n] for i, task_id in enumerate(task_ids)
        }
        has_repeat = any(
            previous_assignments.get(task_id) == user_id
            for task_id, user_id in candidate.items()
        )
        if not has_repeat:
            break

    assignments = []
    for task_id in task_ids:
        scheduled_date = monday + timedelta(days=day_offset[task_id])
        assignments.append((task_id, candidate[task_id], scheduled_date))
    return assignments


class DatabaseManager:
    """Manager asincrono per l'interazione con SQLite."""

    @staticmethod
    async def get_roommates() -> List[Dict[str, Any]]:
        """Recupera tutti i coinquilini (registrati o meno), ordinati per id."""
        query = "SELECT id, name, telegram_id, username FROM users ORDER BY id;"
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
        """Recupera il coinquilino associato a un Telegram User ID, se esiste."""
        query = "SELECT id, name, telegram_id, username FROM users WHERE telegram_id = ?;"
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (telegram_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def claim_roommate_by_id(
        roommate_id: int, telegram_id: int, username: Optional[str]
    ) -> Optional[str]:
        """Associa un Telegram User ID a un coinquilino non ancora registrato.

        Restituisce il nome associato in caso di successo, None se il nome
        risultava già preso da qualcun altro nel frattempo.
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT name FROM users WHERE id = ? AND telegram_id IS NULL;",
                (roommate_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None

            await db.execute(
                "UPDATE users SET telegram_id = ?, username = ? WHERE id = ? AND telegram_id IS NULL;",
                (telegram_id, username, roommate_id),
            )
            await db.commit()
            return row["name"]

    @staticmethod
    async def get_tasks() -> List[Dict[str, Any]]:
        """Restituisce l'elenco delle mansioni di pulizia, in ordine fisso."""
        query = "SELECT id, name, description FROM cleaning_tasks ORDER BY id;"
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_task_assignments_for_week(monday: date) -> Dict[int, int]:
        """Mappa task_id -> user_id assegnato nella settimana che inizia a `monday`.

        Usata da ensure_week_shifts per evitare che un task ricapiti alla
        stessa persona due settimane di fila (vedi compute_week_assignments).
        """
        sunday = monday + timedelta(days=6)
        query = "SELECT task_id, user_id FROM shifts WHERE scheduled_date BETWEEN ? AND ?;"
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(query, (monday.isoformat(), sunday.isoformat())) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}

    @staticmethod
    async def ensure_week_shifts(monday: date) -> None:
        """Genera (se non esistono già) i turni della settimana che inizia a `monday`.

        Un task è considerato "già generato" se ha uno shift in un punto
        QUALSIASI della settimana, non solo nel suo giorno canonico: un
        turno spostato con /reschedule (vedi reschedule_shift) libera il
        giorno originale, e questa funzione viene richiamata di nuovo ad
        ogni /turni e /fatto, non solo dal job del lunedì. Senza questo
        controllo, il giorno liberato verrebbe ririempito con un turno
        duplicato per lo stesso task.
        """
        tasks = await DatabaseManager.get_tasks()
        users = await DatabaseManager.get_roommates()
        task_ids = [t["id"] for t in tasks]
        user_ids = [u["id"] for u in users]
        if not task_ids or not user_ids:
            return

        sunday = monday + timedelta(days=6)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT DISTINCT task_id FROM shifts WHERE scheduled_date BETWEEN ? AND ?;",
                (monday.isoformat(), sunday.isoformat()),
            ) as cursor:
                existing_task_ids = {row[0] for row in await cursor.fetchall()}

            pending_task_ids = [t for t in task_ids if t not in existing_task_ids]
            if not pending_task_ids:
                return

            previous_assignments = await DatabaseManager.get_task_assignments_for_week(
                monday - timedelta(days=7)
            )
            assignments = compute_week_assignments(
                monday,
                pending_task_ids,
                user_ids,
                all_task_ids=task_ids,
                previous_assignments=previous_assignments,
            )
            for task_id, user_id, scheduled_date in assignments:
                await db.execute(
                    "INSERT OR IGNORE INTO shifts (task_id, user_id, scheduled_date) VALUES (?, ?, ?);",
                    (task_id, user_id, scheduled_date.isoformat()),
                )
            await db.commit()

    @staticmethod
    async def get_shifts_for_week(monday: date) -> List[Dict[str, Any]]:
        """Recupera i turni pianificati tra `monday` e la domenica successiva."""
        sunday = monday + timedelta(days=6)
        query = """
        SELECT
            s.id AS shift_id,
            t.name AS task_name,
            u.name AS user_name,
            u.telegram_id AS telegram_id,
            s.scheduled_date,
            s.is_completed
        FROM shifts s
        JOIN cleaning_tasks t ON s.task_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.scheduled_date BETWEEN ? AND ?
        ORDER BY s.scheduled_date ASC;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (monday.isoformat(), sunday.isoformat())) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_current_week_shift_for_user(
        telegram_id: int, monday: date
    ) -> Optional[Dict[str, Any]]:
        """Recupera l'unico turno assegnato all'utente per la settimana che inizia a `monday`.

        La rotazione ciclica assegna esattamente un turno a persona a settimana,
        quindi questo basta per far capire a /fatto quale turno confermare
        senza che l'utente debba specificare un ID.
        """
        sunday = monday + timedelta(days=6)
        query = """
        SELECT
            s.id AS shift_id,
            t.name AS task_name,
            u.name AS user_name,
            s.scheduled_date,
            s.is_completed
        FROM shifts s
        JOIN cleaning_tasks t ON s.task_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE u.telegram_id = ?
          AND s.scheduled_date BETWEEN ? AND ?;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                query, (telegram_id, monday.isoformat(), sunday.isoformat())
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def get_all_time_stats(today: date) -> List[Dict[str, Any]]:
        """Classifica cumulativa: turni completati vs mancati (solo quelli già scaduti) per persona."""
        query = """
        SELECT
            u.name AS user_name,
            COALESCE(SUM(CASE WHEN s.is_completed = 1 THEN 1 ELSE 0 END), 0) AS completed,
            COALESCE(SUM(CASE WHEN s.is_completed = 0 AND s.scheduled_date < ? THEN 1 ELSE 0 END), 0) AS missed
        FROM users u
        LEFT JOIN shifts s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY completed DESC, missed ASC, u.name ASC;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (today.isoformat(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_todays_pending_shifts(target_date: date) -> List[Dict[str, Any]]:
        """Turni di oggi non ancora completati, non ancora notificati e con utente registrato."""
        query = """
        SELECT
            s.id AS shift_id,
            t.name AS task_name,
            u.name AS user_name,
            u.telegram_id AS telegram_id,
            s.scheduled_date
        FROM shifts s
        JOIN cleaning_tasks t ON s.task_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.scheduled_date = ?
          AND s.is_completed = 0
          AND s.notified = 0
          AND u.telegram_id IS NOT NULL;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (target_date.isoformat(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def mark_notified(shift_id: int) -> None:
        """Segna un turno come già notificato per la verifica serale (evita doppi invii)."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE shifts SET notified = 1 WHERE id = ?;", (shift_id,))
            await db.commit()

    @staticmethod
    async def get_shift(shift_id: int) -> Optional[Dict[str, Any]]:
        """Recupera i dettagli completi di un turno tramite il suo ID."""
        query = """
        SELECT
            s.id AS shift_id,
            s.task_id AS task_id,
            s.user_id AS user_id,
            t.name AS task_name,
            u.name AS user_name,
            u.telegram_id AS telegram_id,
            s.scheduled_date,
            s.is_completed,
            s.reschedule_used
        FROM shifts s
        JOIN cleaning_tasks t ON s.task_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (shift_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def reschedule_shift(shift_id: int, new_date: date) -> bool:
        """Sposta un turno fallito a un altro giorno della stessa settimana (una sola volta).

        Resetta `notified` così la verifica serale scatterà di nuovo nel nuovo
        giorno. Restituisce False se il turno non esiste più o se l'occasione
        di spostamento era già stata usata (o consumata con "Non spostare").
        """
        query = """
        UPDATE shifts
        SET scheduled_date = ?, notified = 0, reschedule_used = 1
        WHERE id = ? AND reschedule_used = 0;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            try:
                cursor = await db.execute(query, (new_date.isoformat(), shift_id))
            except aiosqlite.IntegrityError:
                return False
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    async def mark_reschedule_declined(shift_id: int) -> bool:
        """Consuma l'occasione di spostamento senza cambiare data ("Non spostare")."""
        query = """
        UPDATE shifts SET reschedule_used = 1
        WHERE id = ? AND reschedule_used = 0;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(query, (shift_id,))
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    async def get_last_calendar_message(telegram_id: int) -> Optional[int]:
        """Recupera l'ID dell'ultimo messaggio-calendario inviato a un utente, se esiste."""
        query = "SELECT message_id FROM calendar_broadcasts WHERE telegram_id = ?;"
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(query, (telegram_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    @staticmethod
    async def set_last_calendar_message(telegram_id: int, message_id: int) -> None:
        """Registra l'ID dell'ultimo messaggio-calendario inviato a un utente (per poterlo ripulire in seguito)."""
        query = """
        INSERT INTO calendar_broadcasts (telegram_id, message_id) VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET message_id = excluded.message_id;
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(query, (telegram_id, message_id))
            await db.commit()

    @staticmethod
    async def mark_shift_completed(shift_id: int, telegram_id: int) -> bool:
        """Segna un turno come completato dall'utente assegnatario (via telegram_id)."""
        query = """
        UPDATE shifts
        SET is_completed = 1, completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND is_completed = 0
          AND user_id = (SELECT id FROM users WHERE telegram_id = ?);
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(query, (shift_id, telegram_id))
            await db.commit()
            return cursor.rowcount > 0
