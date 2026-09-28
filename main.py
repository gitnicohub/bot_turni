import logging
import sys
from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler, filters
from config import BOT_TOKEN, ADMIN_TELEGRAM_ID
from database.db_setup import init_db
from handlers import (
    start_command,
    help_command,
    list_shifts_command,
    mark_done_command,
    undo_done_command,
    report_command,
    claim_callback,
    verify_callback,
    reschedule_callback,
    audit_update,
    log_command,
)
from scheduler.scheduler_jobs import setup_scheduled_jobs

# Configurazione del logging strutturato
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# httpx a livello INFO logga ogni richiesta con l'URL completo, che contiene
# il token del bot (https://api.telegram.org/bot<TOKEN>/...): lo si alza a WARNING
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Registrati come coinquilino"),
    BotCommand("help", "Mostra i comandi disponibili"),
    BotCommand("turni", "Calendario turni della settimana"),
    BotCommand("fatto", "Segna il tuo turno come completato"),
    BotCommand("annulla", "Annulla un /fatto premuto per errore"),
    BotCommand("report", "Resoconto della settimana scorsa e classifica"),
]

# Visibile nel menu comandi solo nella chat privata dell'admin
ADMIN_COMMANDS = BOT_COMMANDS + [
    BotCommand("log", "Audit log delle azioni degli utenti"),
]

async def post_init(application) -> None:
    """Hook eseguito all'avvio del bot per inizializzare risorse asincrone."""
    logger.info("Esecuzione hook di avvio post_init: verifica database...")
    await init_db()
    await application.bot.set_my_commands(BOT_COMMANDS)
    if ADMIN_TELEGRAM_ID is not None:
        try:
            await application.bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=ADMIN_TELEGRAM_ID)
            )
        except Exception as e:
            # Succede se l'admin non ha mai avviato una chat col bot: /log funziona comunque
            logger.warning("Impossibile impostare il menu comandi dell'admin: %s", e)
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

    # Audit log: gruppo -1, gira su ogni update prima degli handler normali
    application.add_handler(TypeHandler(Update, audit_update), group=-1)

    # Registrazione degli CommandHandler
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("turni", list_shifts_command))
    application.add_handler(CommandHandler("fatto", mark_done_command))
    application.add_handler(CommandHandler("annulla", undo_done_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CallbackQueryHandler(claim_callback, pattern=r"^claim:"))
    application.add_handler(CallbackQueryHandler(verify_callback, pattern=r"^verify:"))
    application.add_handler(CallbackQueryHandler(reschedule_callback, pattern=r"^reschedule:"))

    # /log: solo l'admin, solo in chat privata. Per chiunque altro nessun handler
    # corrisponde e il bot non risponde, come se il comando non esistesse.
    if ADMIN_TELEGRAM_ID is not None:
        application.add_handler(CommandHandler(
            "log",
            log_command,
            filters=filters.User(user_id=ADMIN_TELEGRAM_ID) & filters.ChatType.PRIVATE,
        ))
    else:
        logger.warning("ADMIN_TELEGRAM_ID non impostato: il comando /log è disabilitato.")

    # Configurazione dei task schedulati (se JobQueue è disponibile)
    if application.job_queue:
        setup_scheduled_jobs(application.job_queue)
    else:
        logger.warning("JobQueue non disponibile. Verifica che 'python-telegram-bot[job-queue]' sia installato.")

    logger.info("Bot avviato con successo. In attesa di messaggi (polling)...")
    application.run_polling()

if __name__ == "__main__":
    main()
