import random
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

# (task_id, user_id, scheduled_date) di un turno già assegnato in passato
HistoryRow = Tuple[int, int, date]

# Penalità (in "turni ripetuti equivalenti") per ripetere lo stesso compito
# alla stessa persona a breve distanza. Molto più alte del costo base, così
# una ripetizione ravvicinata viene accettata solo se non c'è alternativa.
REPEAT_LAST_WEEK_PENALTY = 1000
REPEAT_TWO_WEEKS_AGO_PENALTY = 30
# Dare a una persona un secondo compito nella stessa settimana (succede solo
# se i compiti superano i coinquilini, o se un compito viene generato in ritardo)
EXTRA_TASK_IN_WEEK_PENALTY = 500


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _build_cost(
    monday: date,
    task_ids: List[int],
    user_ids: List[int],
    history: Iterable[HistoryRow],
    already_assigned: Dict[int, int],
):
    """Costruisce cost(user, task) a partire dallo storico.

    Costo base: quante volte l'utente ha già fatto quel compito (al quadrato
    marginale, 2c+1), così il carico di ogni compito si distribuisce
    equamente tra tutti nel lungo periodo invece di accumularsi su qualcuno.
    """
    counts: Dict[Tuple[int, int], int] = {}
    last_week_pairs = set()
    two_weeks_ago_pairs = set()
    for task_id, user_id, scheduled in history:
        if scheduled >= monday:
            continue  # solo il passato rispetto alla settimana da generare
        counts[(user_id, task_id)] = counts.get((user_id, task_id), 0) + 1
        weeks_ago = (monday - _monday_of(scheduled)).days // 7
        if weeks_ago == 1:
            last_week_pairs.add((user_id, task_id))
        elif weeks_ago == 2:
            two_weeks_ago_pairs.add((user_id, task_id))

    busy_users: Dict[int, int] = {}
    for user_id in already_assigned.values():
        busy_users[user_id] = busy_users.get(user_id, 0) + 1

    def cost(user_id: int, task_id: int) -> int:
        value = 2 * counts.get((user_id, task_id), 0) + 1
        if (user_id, task_id) in last_week_pairs:
            value += REPEAT_LAST_WEEK_PENALTY
        if (user_id, task_id) in two_weeks_ago_pairs:
            value += REPEAT_TWO_WEEKS_AGO_PENALTY
        value += EXTRA_TASK_IN_WEEK_PENALTY * busy_users.get(user_id, 0)
        return value

    return cost


def _hungarian(matrix: List[List[float]]) -> List[int]:
    """Assegnazione a costo minimo (algoritmo ungherese, O(n^2 * m)).

    `matrix` ha n righe (compiti) e m >= n colonne (posti disponibili).
    Restituisce, per ogni riga, l'indice della colonna assegnata.
    """
    n, m = len(matrix), len(matrix[0])
    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = matrix[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    return result


def _pick_assignment(task_ids, user_ids, cost, rng) -> Dict[int, int]:
    """Assegnazione ottima (task_id -> user_id) con spareggio casuale.

    Se i compiti sono più dei coinquilini, ogni persona compare più volte tra
    i posti disponibili; ogni compito in più alla stessa persona costa
    EXTRA_TASK_IN_WEEK_PENALTY, quindi il carico resta il più equo possibile.
    Un piccolo rumore casuale (la cui somma resta sotto 1, il costo minimo
    dei costi interi) decide solo tra assegnazioni di costo identico.
    """
    rounds = -(-len(task_ids) // len(user_ids))
    slots = [(user, k) for k in range(rounds) for user in user_ids]
    noise = 0.9 / len(task_ids)
    matrix = [
        [cost(user, task) + EXTRA_TASK_IN_WEEK_PENALTY * k + rng.random() * noise for user, k in slots]
        for task in task_ids
    ]
    columns = _hungarian(matrix)
    return {task: slots[col][0] for task, col in zip(task_ids, columns)}


def compute_week_assignments(
    monday: date,
    task_ids: List[int],
    user_ids: List[int],
    all_task_ids: Optional[List[int]] = None,
    history: Optional[Iterable[HistoryRow]] = None,
    already_assigned: Optional[Dict[int, int]] = None,
    rng: Optional[random.Random] = None,
) -> List[tuple]:
    """Assegna i turni della settimana che inizia a `monday` tenendo conto dello storico.

    Per ogni combinazione persona-compito calcola un costo basato su quante
    volte quella persona ha già fatto quel compito (vedi `_build_cost`), con
    forti penalità se è lo stesso della settimana scorsa o di due settimane fa.
    Tra tutte le assegnazioni possibili sceglie a caso una di quelle a costo
    minimo: il risultato è equo nel lungo periodo ma non prevedibile.

    `history`: turni passati come (task_id, user_id, scheduled_date).
    `already_assigned`: task_id -> user_id dei turni già presenti in questa
    settimana (quando `task_ids` è solo un sottoinsieme da completare).
    `all_task_ids`: elenco completo ordinato dei compiti, per calcolare il
    giorno di ciascuno (monday + indice) anche se `task_ids` è filtrato.
    Restituisce una lista di (task_id, user_id, scheduled_date).
    """
    if not task_ids or not user_ids:
        return []

    rng = rng or random
    order_reference = all_task_ids if all_task_ids is not None else task_ids
    day_offset = {tid: i for i, tid in enumerate(order_reference)}

    cost = _build_cost(monday, task_ids, user_ids, history or [], already_assigned or {})
    chosen = _pick_assignment(list(task_ids), list(user_ids), cost, rng)

    return [
        (task_id, chosen[task_id], monday + timedelta(days=day_offset[task_id]))
        for task_id in task_ids
    ]
