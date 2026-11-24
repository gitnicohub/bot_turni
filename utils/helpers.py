import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

PUNISHMENT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
PUNISHMENT_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".oga", ".opus", ".wav", ".m4a"}

GOOGLE_CALENDAR_BASE_URL = "https://calendar.google.com/calendar/render"
WEEKDAY_LABELS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

# Insulti goliardici per il turno mancato: tono esagerato e da presa in giro
# tra coinquilini, senza bestemmie né riferimenti a familiari.
PUNISHMENT_INSULTS = [
    "🚨 *{name}*, il turno *{task}* ti aspettava e tu l'hai bidonato come un appuntamento al buio andato male. Vergognati, campione della latitanza! 🏆🙈",
    "😤 Allora *{name}*, il *{task}* è ancora lì, intonso, che ti guarda deluso. Sei ufficialmente il re/la regina della procrastinazione domestica! 👑🦥",
    "🧻 *{name}*, hai skippato *{task}* con la stessa nonchalance con cui skippi le sveglie. La casa piange, i coinquilini pure. 😭🏠",
    "🐌 Più lento di *{name}* sul turno di *{task}* c'è solo una lumaca in pensione. Fatti perdonare, o la fama ti precede! 🐌📉",
    "🎭 *{name}*, il tuo *{task}* non pervenuto merita un Oscar nella categoria 'Miglior sparizione improvvisa'. Applausi. 👏🫠",
]


def monday_of(day: date) -> date:
    """Restituisce il lunedì della settimana a cui appartiene `day`."""
    return day - timedelta(days=day.weekday())


def escape_markdown(text: str) -> str:
    """Esegue l'escape dei caratteri speciali per Telegram MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)


def build_google_calendar_link(task_name: str, scheduled_date: Any) -> str:
    """Genera un link precompilato per aggiungere il turno a Google Calendar."""
    if isinstance(scheduled_date, str):
        day = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
    else:
        day = scheduled_date

    start = day.strftime("%Y%m%d")
    end = (day + timedelta(days=1)).strftime("%Y%m%d")
    params = {
        "action": "TEMPLATE",
        "text": f"Turno pulizie: {task_name}",
        "dates": f"{start}/{end}",
        "details": f"Promemoria turno di pulizia '{task_name}' assegnato dal Bot Turni di casa.",
    }
    return f"{GOOGLE_CALENDAR_BASE_URL}?{urlencode(params)}"


def pick_random_punishment_image(images_dir: str) -> Optional[Path]:
    """Sceglie a caso un file immagine dalla cartella delle immagini punitive.

    Restituisce None se la cartella non esiste o non contiene immagini valide.
    """
    folder = Path(images_dir)
    if not folder.is_dir():
        return None

    images = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in PUNISHMENT_IMAGE_EXTENSIONS
    ]
    if not images:
        return None

    return random.choice(images)


def pick_random_punishment_audio(audio_dir: str) -> Optional[Path]:
    """Sceglie a caso un file audio dalla cartella delle immagini punitive.

    Restituisce None se la cartella non esiste o non contiene audio validi.
    """
    folder = Path(audio_dir)
    if not folder.is_dir():
        return None

    audios = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in PUNISHMENT_AUDIO_EXTENSIONS
    ]
    if not audios:
        return None

    return random.choice(audios)


RANK_MEDALS = ["🥇", "🥈", "🥉"]
WEEKDAY_EMOJIS = ["🔥", "🌊", "🌪️", "⚡", "🎉", "🌈", "🌙"]
SEPARATOR = "━━━━━━━━━━━━━━━"


NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
TRASH_TITLE = "Kosettine settimanine"


def _trash_emoji_by_name() -> Dict[str, str]:
    from config import TRASH_CHORES
    return {name: emoji for name, emoji in TRASH_CHORES}


def format_trash_list(trash: List[Dict[str, Any]]) -> str:
    """Formatta la lista Kosettine settimanine: elenco numerato con l'assegnatario di ciascun compito."""
    if not trash:
        return f"🗑️ Nessuna lista *{TRASH_TITLE}* generata per questa settimana."

    monday = datetime.strptime(trash[0]["week_start"], "%Y-%m-%d").date()
    sunday = monday + timedelta(days=6)
    emojis = _trash_emoji_by_name()

    lines = [
        f"🗑️✨ *{TRASH_TITLE.upper()}* ✨🗑️",
        f"_{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}_",
        SEPARATOR,
    ]
    for i, t in enumerate(trash):
        number = NUMBER_EMOJIS[i] if i < len(NUMBER_EMOJIS) else f"{i + 1}."
        emoji = emojis.get(t["chore_name"], "🗑️")
        status = "✅ Fatto" if t.get("is_completed") else "🕒 In attesa"
        lines.append(f"{number} {emoji} {t['chore_name']}")
        lines.append(f"   ➜ 👤 *{t['user_name']}*  {status}\n")

    lines.append(SEPARATOR)
    lines.append("💡 Quando hai finito usa `/fattoimmondizia`: domenica alle 23:00 ti chiedo conferma se risulta in attesa.")
    return "\n".join(lines)


def _completion_date(completed_at: Optional[str], tz_name: str) -> Optional[date]:
    """Data locale di completamento: `completed_at` è salvato in UTC da SQLite (CURRENT_TIMESTAMP)."""
    if not completed_at:
        return None
    import pytz
    moment = datetime.strptime(completed_at[:19], "%Y-%m-%d %H:%M:%S")
    return pytz.utc.localize(moment).astimezone(pytz.timezone(tz_name)).date()


def format_user_history(
    user_name: str,
    history: Dict[str, List[Dict[str, Any]]],
    today: date,
    tz_name: str,
) -> List[str]:
    """Storico di turni e Kosettine di un utente, spezzato in messaggi sotto il limite di Telegram.

    Fatti: data di completamento. Non fatti: data del turno (o settimana per le
    Kosettine), come mancati se già scaduti o in attesa se ancora in corso.
    """
    current_monday = monday_of(today)
    emojis = _trash_emoji_by_name()

    def line(item: Dict[str, Any], label: str, expired: bool, day_text: str) -> str:
        if item["is_completed"]:
            done_on = _completion_date(item.get("completed_at"), tz_name)
            verb = "recuperato" if item.get("recovered") else "fatto"
            when = f" il {done_on.strftime('%d/%m/%Y')}" if done_on else ""
            return f"✅ {label} — {verb}{when}"
        if expired:
            return f"❌ {label} — non fatto ({day_text})"
        return f"🕒 {label} — in attesa ({day_text})"

    shift_lines, trash_lines = [], []
    for s in history["shifts"]:
        day = datetime.strptime(s["day"], "%Y-%m-%d").date()
        shift_lines.append(line(
            s, f"`{s['name'].upper()}`", day < current_monday, f"previsto {day.strftime('%d/%m/%Y')}"
        ))
    for t in history["trash"]:
        week = datetime.strptime(t["day"], "%Y-%m-%d").date()
        label = f"{emojis.get(t['name'], '🗑️')} {t['name']}"
        trash_lines.append(line(t, label, week < current_monday, f"settimana del {week.strftime('%d/%m/%Y')}"))

    def totals(items: List[Dict[str, Any]]) -> str:
        done = sum(1 for i in items if i["is_completed"])
        missed = sum(
            1 for i in items
            if not i["is_completed"] and datetime.strptime(i["day"], "%Y-%m-%d").date() < current_monday
        )
        return f"_{done} ✅ / {missed} ❌ / {len(items) - done - missed} 🕒_"

    lines = [f"📜✨ *STORICO DI {user_name.upper()}* ✨📜", SEPARATOR, f"🧽 *TURNI* {totals(history['shifts'])}\n"]
    lines += shift_lines or ["Nessun turno ancora."]
    lines += ["", SEPARATOR, f"🗑️ *KOSETTINE SETTIMANINE* {totals(history['trash'])}\n"]
    lines += trash_lines or ["Nessuna Kosettina ancora."]

    messages, current = [], ""
    for ln in lines:
        if current and len(current) + len(ln) + 1 > 3800:
            messages.append(current)
            current = ""
        current += ("\n" if current else "") + ln
    messages.append(current)
    return messages


def format_weekly_report(
    monday: date,
    week_shifts: List[Dict[str, Any]],
    ranking: List[Dict[str, Any]],
    trash: Optional[List[Dict[str, Any]]] = None,
    trash_ranking: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Formatta il resoconto della settimana appena conclusa (esito turni + classifica generale).

    Stesso stile a blocchi giorno-per-giorno di format_weekly_calendar, per
    coerenza visiva tra i due messaggi. `trash` / `trash_ranking` (opzionali)
    aggiungono esito e classifica della lista Kosettine settimanine.
    """
    sunday = monday + timedelta(days=6)
    lines = [
        "📊✨ *RESOCONTO SETTIMANALE* ✨📊",
        f"_{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}_",
        SEPARATOR,
    ]

    if not week_shifts:
        lines.append("🧹✨ Nessun turno era stato generato questa settimana.\n")
    else:
        for s in week_shifts:
            day = datetime.strptime(s["scheduled_date"], "%Y-%m-%d").date()
            weekday_label = WEEKDAY_LABELS[day.weekday()]
            day_emoji = WEEKDAY_EMOJIS[day.weekday()]
            status = "✅ Completato" if s.get("is_completed") else "❌ Non completato"

            lines.append(f"{day_emoji} *{weekday_label.upper()}*")
            lines.append(f"   🧽 `{s['task_name'].upper()}` ➜ 👤 *{s['user_name']}*")
            lines.append(f"   {status}\n")

    lines.append(SEPARATOR)
    lines.append("🏆 *CLASSIFICA GENERALE* _(completati ✅ / mancati ❌ / in attesa 🕒)_\n")
    for i, r in enumerate(ranking):
        prefix = RANK_MEDALS[i] if i < len(RANK_MEDALS) else f"{i + 1}."
        row = f"{prefix} *{r['user_name']}* — {r['completed']} ✅ / {r['missed']} ❌"
        if r.get("pending"):
            row += f" / {r['pending']} 🕒"
        lines.append(row)

    if trash:
        lines.append("")
        lines.append(SEPARATOR)
        lines.append(f"🗑️ *{TRASH_TITLE.upper()}* _(settimana conclusa)_\n")
        emojis = _trash_emoji_by_name()
        for i, t in enumerate(trash):
            number = NUMBER_EMOJIS[i] if i < len(NUMBER_EMOJIS) else f"{i + 1}."
            status = "✅ Fatto" if t.get("is_completed") else "❌ Non fatto"
            lines.append(f"{number} {emojis.get(t['chore_name'], '🗑️')} {t['chore_name']}")
            lines.append(f"   ➜ 👤 *{t['user_name']}*  {status}\n")

    if trash_ranking and any(r["completed"] or r["missed"] or r.get("pending") for r in trash_ranking):
        lines.append(SEPARATOR)
        lines.append("🗑️🏆 *CLASSIFICA KOSETTINE* _(fatte ✅ / mancate ❌ / in attesa 🕒)_\n")
        for i, r in enumerate(trash_ranking):
            prefix = RANK_MEDALS[i] if i < len(RANK_MEDALS) else f"{i + 1}."
            row = f"{prefix} *{r['user_name']}* — {r['completed']} ✅ / {r['missed']} ❌"
            if r.get("pending"):
                row += f" / {r['pending']} 🕒"
            lines.append(row)

    return "\n".join(lines)


def format_weekly_calendar(shifts: List[Dict[str, Any]]) -> str:
    """Formatta il calendario settimanale dei turni, raggruppato per giorno."""
    if not shifts:
        return "🧹✨ Nessun turno generato per questa settimana."

    # Il primo turno può essere stato spostato in avanti (es. a mercoledì):
    # l'intestazione deve comunque partire dal lunedì della sua settimana.
    monday = monday_of(min(datetime.strptime(s["scheduled_date"], "%Y-%m-%d").date() for s in shifts))
    sunday = monday + timedelta(days=6)

    lines = [
        f"📅✨ *CALENDARIO TURNI* ✨📅",
        f"_{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}_",
        SEPARATOR,
    ]

    for s in shifts:
        day = datetime.strptime(s["scheduled_date"], "%Y-%m-%d").date()
        weekday_label = WEEKDAY_LABELS[day.weekday()]
        day_emoji = WEEKDAY_EMOJIS[day.weekday()]
        status = "✅ Completato" if s.get("is_completed") else "🕒 In attesa"

        lines.append(f"{day_emoji} *{weekday_label.upper()}*")
        lines.append(f"   🧽 `{s['task_name'].upper()}` ➜ 👤 *{s['user_name']}*")
        lines.append(f"   {status}\n")

    lines.append(SEPARATOR)
    lines.append("💡 Usa `/fatto` oppure rispondi al promemoria delle 23:00 per confermare.")
    return "\n".join(lines)
