import logging
from datetime import datetime
import pytz
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes
from config import ADMIN_TELEGRAM_ID, TIMEZONE
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

DEFAULT_LOG_ENTRIES = 30
MAX_LOG_ENTRIES = 500
# Limite Telegram: 4096 caratteri per messaggio, si tiene un margine
MAX_MESSAGE_LENGTH = 4000

# Tipi di contenuto non testuale, nell'ordine in cui vengono cercati sul messaggio
_ATTACHMENT_TYPES = [
    "photo", "voice", "audio", "video", "video_note", "animation",
    "sticker", "document", "location", "contact", "poll",
]


def _describe_message(message) -> tuple:
    """Restituisce (event_type, content) per un messaggio ricevuto."""
    if message.text:
        event_type = "comando" if message.text.startswith("/") else "messaggio"
        return event_type, message.text

    for attr in _ATTACHMENT_TYPES:
        if getattr(message, attr, None):
            content = f"[{attr}]"
            if message.caption:
                content += f" {message.caption}"
            return "allegato", content

    return "altro", "[contenuto non riconosciuto]"


def _describe_update(update: Update) -> tuple:
    """Restituisce (event_type, content) per qualsiasi update ricevuto dal bot."""
    if update.callback_query:
        return "pulsante", update.callback_query.data
    if update.edited_message:
        _, content = _describe_message(update.edited_message)
        return "modifica", content
    if update.message:
        return _describe_message(update.message)
    if update.my_chat_member:
        status = update.my_chat_member.new_chat_member.status
        return "stato_chat", f"bot {status}"
    return "altro", type(update).__name__


async def audit_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra nell'audit log ogni update ricevuto, prima che venga gestito dagli altri handler.

    Registrato nel gruppo -1: non blocca mai la gestione normale dell'update,
    e un errore di scrittura viene solo loggato.
    """
    user = update.effective_user
    chat = update.effective_chat
    event_type, content = _describe_update(update)
    try:
        await DatabaseManager.add_audit_entry(
            telegram_id=user.id if user else None,
            username=user.username if user else None,
            full_name=user.full_name if user else None,
            chat_id=chat.id if chat else None,
            event_type=event_type,
            content=content,
        )
    except Exception as e:
        logger.warning("Impossibile scrivere nell'audit log: %s", e)

    logger.info(
        "AUDIT %s (@%s, ID %s) %s: %s",
        user.full_name if user else "?",
        user.username if user else "-",
        user.id if user else "-",
        event_type,
        content,
    )


def _format_entry(entry: dict, tz) -> str:
    created_at = datetime.strptime(entry["created_at"], "%Y-%m-%d %H:%M:%S")
    local_time = pytz.utc.localize(created_at).astimezone(tz)
    who = entry["roommate_name"] or entry["full_name"] or "sconosciuto"
    if entry["username"]:
        who += f" (@{entry['username']})"
    if not entry["roommate_name"]:
        who += f" [ID {entry['telegram_id']}, non registrato]"
    return f"{local_time.strftime('%d/%m %H:%M')} · {who} · {entry['event_type']}: {entry['content']}"


def _is_admin_private_chat(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    return (
        ADMIN_TELEGRAM_ID is not None
        and user is not None
        and chat is not None
        and user.id == ADMIN_TELEGRAM_ID
        and chat.type == ChatType.PRIVATE
    )


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/log [n]: mostra le ultime n azioni degli utenti. Solo per l'admin, solo in chat privata.

    L'handler è già filtrato in main.py su ADMIN_TELEGRAM_ID; il controllo
    qui è una seconda barriera. A chiunque altro il bot non risponde nulla,
    come se il comando non esistesse.
    """
    if not _is_admin_private_chat(update):
        return

    limit = DEFAULT_LOG_ENTRIES
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), MAX_LOG_ENTRIES))

    entries = await DatabaseManager.get_audit_entries(limit)
    if not entries:
        await update.message.reply_text("📭 L'audit log è vuoto.")
        return

    tz = pytz.timezone(TIMEZONE)
    lines = [_format_entry(e, tz) for e in entries]

    # Spezza su più messaggi per rispettare il limite di lunghezza di Telegram
    chunk = f"🕵️ Ultime {len(entries)} azioni:\n"
    for line in lines:
        line = line[:MAX_MESSAGE_LENGTH]
        if len(chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk)
