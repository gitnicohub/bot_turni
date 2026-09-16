import logging
import sys
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN
from database.db_setup import init_db
from handlers import (
    start_command,
    help_command,
    list_shifts_command,
    mark_done_command,
    claim_callback,
    verify_callback,
    reschedule_callback,
)
from scheduler.scheduler_jobs import setup_scheduled_jobs

# Configurazione del logging strutturato
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Registrati come coinquilino"),
    BotCommand("help", "Mostra i comandi disponibili"),
    BotCommand("turni", "Calendario turni della settimana"),
    BotCommand("fatto", "Segna il tuo turno come completato"),
]

async def post_init(application) -> None:
    """Hook eseguito all'avvio del bot per inizializzare risorse asincrone."""
    logger.info("Esecuzione hook di avvio post_init: verifica database...")
    await init_db()
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Inizializzazione completata.")

def main() -> None:
    """Inizializza l'applicazione Telegram, registra gli handler e avvia il polling."""
    if not BOT_TOKEN or BOT_TOKEN == "inserisci_qui_il_tuo_token":
        logger.error(
            "ERRORE: TELEGRAM_BOT_TOKEN non valido o mancante! "
            "Copia .env.example in .env e inserisci il token ottenuto da @BotFather."
        )
        sys.exit(1)

    # Creazione dell'applicazione PTB (v20+) con supporto nativo a JobQueue (APScheduler)
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Registrazione degli CommandHandler
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("turni", list_shifts_command))
    application.add_handler(CommandHandler("fatto", mark_done_command))
    application.add_handler(CallbackQueryHandler(claim_callback, pattern=r"^claim:"))
    application.add_handler(CallbackQueryHandler(verify_callback, pattern=r"^verify:"))
    application.add_handler(CallbackQueryHandler(reschedule_callback, pattern=r"^reschedule:"))

    # Configurazione dei task schedulati (se JobQueue è disponibile)
    if application.job_queue:
        setup_scheduled_jobs(application.job_queue)
    else:
        logger.warning("JobQueue non disponibile. Verifica che 'python-telegram-bot[job-queue]' sia installato.")

    logger.info("Bot avviato con successo. In attesa di messaggi (polling)...")
    application.run_polling()

if __name__ == "__main__":
    main()
