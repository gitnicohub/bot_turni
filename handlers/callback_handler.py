import logging
import random
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import PUNISHMENT_IMAGES_DIR
from database.db_manager import DatabaseManager
from utils.helpers import PUNISHMENT_INSULTS, pick_random_punishment_image

logger = logging.getLogger(__name__)

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
