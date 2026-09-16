import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import PUNISHMENT_IMAGES_DIR
from database.db_manager import DatabaseManager
from utils.helpers import (
    PUNISHMENT_INSULTS,
    WEEKDAY_LABELS,
    pick_random_punishment_image,
    pick_random_punishment_audio,
    format_weekly_calendar,
    monday_of,
)

logger = logging.getLogger(__name__)

def _build_reschedule_keyboard(shift_id: int, scheduled_date):
    """Bottoni per spostare il turno a un giorno successivo della stessa settimana.

    Restituisce None se il turno fallito è già di domenica (nessun giorno
    successivo disponibile nella settimana).
    """
    sunday = scheduled_date + timedelta(days=6 - scheduled_date.weekday())
    day = scheduled_date + timedelta(days=1)
    buttons = []
    while day <= sunday:
        label = f"📅 {WEEKDAY_LABELS[day.weekday()]} {day.strftime('%d/%m')}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"reschedule:{shift_id}:{day.isoformat()}")])
        day += timedelta(days=1)

    if not buttons:
        return None

    buttons.append([InlineKeyboardButton("🙅 Non spostare", callback_data=f"reschedule:{shift_id}:skip")])
    return InlineKeyboardMarkup(buttons)

async def claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il click su un nome nella tastiera di /start: associa telegram_id al nome."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user:
        return

    existing = await DatabaseManager.get_user_by_telegram_id(user.id)
    if existing:
        await query.edit_message_text(
            f"Sei già registrato come *{existing['name']}*.", parse_mode=ParseMode.MARKDOWN
        )
        return

    roommate_id = int(query.data.split(":")[1])
    claimed_name = await DatabaseManager.claim_roommate_by_id(roommate_id, user.id, user.username)

    if not claimed_name:
        await query.edit_message_text(
            "⚠️ Questo nome è già stato scelto da qualcun altro nel frattempo. Riprova con /start."
        )
        return

    logger.info("Coinquilino registrato: %s (Telegram ID: %d)", claimed_name, user.id)
    await query.edit_message_text(
        f"✅ Registrato come *{claimed_name}*!\nUsa /turni per vedere il calendario della settimana.",
        parse_mode=ParseMode.MARKDOWN
    )

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il click su ✅/❌ del promemoria serale delle 23:00."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user:
        return

    _, shift_id_str, outcome = query.data.split(":")
    shift_id = int(shift_id_str)

    shift = await DatabaseManager.get_shift(shift_id)
    if not shift or shift["telegram_id"] != user.id:
        await query.edit_message_text("⚠️ Questo turno non ti risulta assegnato o non esiste più.")
        return

    if outcome == "done":
        success = await DatabaseManager.mark_shift_completed(shift_id, user.id)
        if success:
            await query.edit_message_text(
                f"✅ Ottimo lavoro *{shift['user_name']}*! Turno *{shift['task_name']}* confermato come completato.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text("⚠️ Questo turno risultava già segnato come completato.")
        return

    # outcome == "fail"
    insult = random.choice(PUNISHMENT_INSULTS).format(
        name=shift["user_name"], task=shift["task_name"]
    )
    await query.edit_message_text(insult, parse_mode=ParseMode.MARKDOWN)

    image_path = pick_random_punishment_image(PUNISHMENT_IMAGES_DIR)
    if image_path:
        try:
            with open(image_path, "rb") as photo_file:
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=photo_file,
                    caption="🚨 Prova fotografica della tua vergogna odierna. Fatti perdonare domani! 🚨"
                )
        except Exception as e:
            logger.warning("Impossibile inviare la foto punitiva a %s: %s", user.id, e)
    else:
        logger.warning(
            "Nessuna immagine punitiva trovata in %s: nessuna foto inviata.", PUNISHMENT_IMAGES_DIR
        )

    audio_path = pick_random_punishment_audio(PUNISHMENT_IMAGES_DIR)
    if audio_path:
        try:
            with open(audio_path, "rb") as voice_file:
                await context.bot.send_voice(
                    chat_id=user.id,
                    voice=voice_file,
                    caption="🎙️ Messaggio vocale della tua vergogna odierna. Fatti perdonare domani! 🎙️"
                )
        except Exception as e:
            logger.warning("Impossibile inviare l'audio punitivo a %s: %s", user.id, e)
    else:
        logger.warning(
            "Nessun audio punitivo trovato in %s: nessun vocale inviato.", PUNISHMENT_IMAGES_DIR
        )

    if not shift["reschedule_used"]:
        scheduled_date = datetime.strptime(shift["scheduled_date"], "%Y-%m-%d").date()
        keyboard = _build_reschedule_keyboard(shift_id, scheduled_date)
        if keyboard:
            await context.bot.send_message(
                chat_id=user.id,
                text="🔁 Vuoi spostare questo turno a un altro giorno della settimana?",
                reply_markup=keyboard,
            )

async def reschedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce la scelta del giorno in cui spostare un turno fallito (o il rifiuto)."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user:
        return

    _, shift_id_str, choice = query.data.split(":")
    shift_id = int(shift_id_str)

    shift = await DatabaseManager.get_shift(shift_id)
    if not shift or shift["telegram_id"] != user.id:
        await query.edit_message_text("⚠️ Questo turno non ti risulta assegnato o non esiste più.")
        return

    if shift["reschedule_used"]:
        await query.edit_message_text("⚠️ Avevi già deciso cosa fare di questo turno.")
        return

    if choice == "skip":
        await DatabaseManager.mark_reschedule_declined(shift_id)
        await query.edit_message_text("👍 Ok, il turno resta dov'era.")
        return

    new_date = datetime.strptime(choice, "%Y-%m-%d").date()
    success = await DatabaseManager.reschedule_shift(shift_id, new_date)
    if not success:
        await query.edit_message_text("⚠️ Impossibile spostare il turno (forse era già stato deciso). Riprova più tardi.")
        return

    weekday_label = WEEKDAY_LABELS[new_date.weekday()]
    await query.edit_message_text(
        f"✅ Turno *{shift['task_name']}* spostato a *{weekday_label} {new_date.strftime('%d/%m')}*.",
        parse_mode=ParseMode.MARKDOWN
    )

    monday = monday_of(new_date)
    week_shifts = await DatabaseManager.get_shifts_for_week(monday)
    calendar_text = format_weekly_calendar(week_shifts)
    roommates = await DatabaseManager.get_roommates()
    for r in roommates:
        if not r["telegram_id"]:
            continue

        old_message_id = await DatabaseManager.get_last_calendar_message(r["telegram_id"])
        if old_message_id:
            try:
                await context.bot.delete_message(chat_id=r["telegram_id"], message_id=old_message_id)
            except Exception:
                pass  # messaggio già cancellato o troppo vecchio: si prosegue comunque

        try:
            sent = await context.bot.send_message(
                chat_id=r["telegram_id"], text=calendar_text, parse_mode=ParseMode.MARKDOWN
            )
            await DatabaseManager.set_last_calendar_message(r["telegram_id"], sent.message_id)
        except Exception as e:
            logger.warning("Impossibile inviare il calendario aggiornato a %s: %s", r["telegram_id"], e)
