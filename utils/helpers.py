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


def format_weekly_report(monday: date, week_shifts: List[Dict[str, Any]], ranking: List[Dict[str, Any]]) -> str:
    """Formatta il resoconto della settimana appena conclusa (esito turni + classifica generale).

    Stesso stile a blocchi giorno-per-giorno di format_weekly_calendar, per
    coerenza visiva tra i due messaggi.
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
    lines.append("🏆 *CLASSIFICA GENERALE* _(completati ✅ / mancati ❌)_\n")
    for i, r in enumerate(ranking):
        prefix = RANK_MEDALS[i] if i < len(RANK_MEDALS) else f"{i + 1}."
        lines.append(f"{prefix} *{r['user_name']}* — {r['completed']} ✅ / {r['missed']} ❌")

    return "\n".join(lines)


def format_weekly_calendar(shifts: List[Dict[str, Any]]) -> str:
    """Formatta il calendario settimanale dei turni, raggruppato per giorno."""
    if not shifts:
        return "🧹✨ Nessun turno generato per questa settimana."

    monday = min(datetime.strptime(s["scheduled_date"], "%Y-%m-%d").date() for s in shifts)
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
