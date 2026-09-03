import logging
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import TIMEZONE
from database.db_manager import DatabaseManager
from utils.helpers import format_weekly_calendar, build_google_calendar_link

logger = logging.getLogger(__name__)

def _current_monday() -> datetime.date:
    today = datetime.now(pytz.timezone(TIMEZONE)).date()
    return today - timedelta(days=today.weekday())

async def list_shifts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra il calendario settimanale dei turni, generandolo se non esiste ancora."""
    monday = _current_monday()
    await DatabaseManager.ensure_week_shifts(monday)
    shifts = await DatabaseManager.get_shifts_for_week(monday)

    text = format_weekly_calendar(shifts)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    user = update.effective_user
    if not user:
        return

    my_shifts = [s for s in shifts if s.get("telegram_id") == user.id]
    if my_shifts:
        keyboard = [
            [InlineKeyboardButton(
                f"📅 Aggiungi '{s['task_name']}' al Calendar",
                url=build_google_calendar_link(s["task_name"], s["scheduled_date"])
            )]
            for s in my_shifts
        ]
        await update.message.reply_text(
            "I tuoi turni di questa settimana:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def mark_done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Segna come completato il turno di questa settimana assegnato all'utente (/fatto, senza argomenti)."""
    user = update.effective_user
    if not user:
        return

    registered = await DatabaseManager.get_user_by_telegram_id(user.id)
    if not registered:
        await update.message.reply_text(
            "⚠️ Non risulti ancora registrato. Usa /start per selezionare il tuo nome tra i coinquilini."
        )
        return

    monday = _current_monday()
    await DatabaseManager.ensure_week_shifts(monday)
    shift = await DatabaseManager.get_current_week_shift_for_user(user.id, monday)

    if not shift:
        await update.message.reply_text(
            f"🧹 Non risulta nessun turno assegnato a *{registered['name']}* questa settimana.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if shift["is_completed"]:
        await update.message.reply_text(
            f"✅ Il tuo turno di questa settimana (*{shift['task_name']}*) risultava già completato.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    success = await DatabaseManager.mark_shift_completed(shift["shift_id"], user.id)
    if success:
        logger.info("Turno %d (%s) completato da %s", shift["shift_id"], shift["task_name"], registered["name"])
        await update.message.reply_text(
            f"✅ Ottimo lavoro *{registered['name']}*! Turno *{shift['task_name']}* segnato come completato.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("⚠️ Impossibile completare il turno. Riprova più tardi.")
