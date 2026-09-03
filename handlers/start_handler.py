import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il comando /start: mostra la tastiera per associare il proprio nome."""
    user = update.effective_user
    if not user:
        return

    existing = await DatabaseManager.get_user_by_telegram_id(user.id)
    if existing:
        await update.message.reply_text(
            f"👋 Bentornato *{existing['name']}*! Sei già registrato.\n\n"
            "Usa /turni per vedere il calendario della settimana.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    roommates = await DatabaseManager.get_roommates()
    available = [r for r in roommates if r["telegram_id"] is None]

    if not available:
        await update.message.reply_text(
            "⚠️ Tutti i coinquilini risultano già registrati. "
            "Se pensi sia un errore, contatta chi gestisce il bot."
        )
        return

    keyboard = [
        [InlineKeyboardButton(r["name"], callback_data=f"claim:{r['id']}")]
        for r in available
    ]

    await update.message.reply_text(
        "👋 Ciao! Sono il bot per la gestione dei *turni di pulizia* della casa 🏠✨\n\n"
        "Chi sei tra i coinquilini? Scegli il tuo nome qui sotto:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il comando /help."""
    help_text = (
        "ℹ️ *Guida Bot Turni Pulizia*\n\n"
        "• `/start`: Associa il tuo account Telegram al tuo nome tra i coinquilini.\n"
        "• `/turni`: Visualizza il calendario settimanale dei turni con link Google Calendar.\n"
        "• `/fatto`: Segna come completato il turno assegnato a te questa settimana (il bot lo capisce da solo).\n"
        "• Ogni sera alle 23:00 riceverai un promemoria con bottoni ✅/❌ per confermare il turno del giorno.\n"
        "• Ogni sabato mattina alle 9:00 arriva il resoconto settimanale con la classifica generale.\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
