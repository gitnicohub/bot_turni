import logging
import datetime
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import TIMEZONE
from database.db_manager import DatabaseManager
from utils.helpers import format_weekly_report, format_trash_list

logger = logging.getLogger(__name__)

async def generate_weekly_shifts_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task settimanale: genera i turni della settimana corrente e la lista Kosettine, e manda la lista a tutti."""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    monday = today - datetime.timedelta(days=today.weekday())
    await DatabaseManager.ensure_week_shifts(monday)
    logger.info("Turni della settimana generati a partire da %s.", monday)

    # Se la lista esisteva già (es. generata da un /turni anticipato) viene
    # comunque mandata: il lunedì tutti la ricevono una volta sola.
    await DatabaseManager.ensure_week_trash(monday)
    text = format_trash_list(await DatabaseManager.get_trash_for_week(monday))
    for r in await DatabaseManager.get_roommates():
        if not r["telegram_id"]:
            continue
        try:
            await context.bot.send_message(chat_id=r["telegram_id"], text=text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning("Impossibile inviare la lista Kosettine a %s: %s", r["telegram_id"], e)

async def sunday_trash_verification_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Domenica 23:00: chiede conferma dei compiti Kosettine ancora in attesa."""
    logger.info("Esecuzione job: verifica domenicale Kosettine.")
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    monday = today - datetime.timedelta(days=today.weekday())

    for t in await DatabaseManager.get_pending_trash_for_week(monday):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Fatto", callback_data=f"trash:{t['assignment_id']}:done"),
            InlineKeyboardButton("❌ Non fatto", callback_data=f"trash:{t['assignment_id']}:fail"),
        ]])
        try:
            await context.bot.send_message(
                chat_id=t["telegram_id"],
                text=f"🗑️ Ehi *{t['user_name']}*, questa settimana toccava a te: *{t['chore_name']}*. L'hai fatto?",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning("Impossibile inviare la verifica Kosettine all'utente %s: %s", t["telegram_id"], e)

async def evening_verification_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task giornaliero (23:00): chiede conferma dei turni di oggi con bottoni ✅/❌."""
    logger.info("Esecuzione job: verifica serale turni.")
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    shifts = await DatabaseManager.get_todays_pending_shifts(today)

    for s in shifts:
        shift_id = s["shift_id"]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completato", callback_data=f"verify:{shift_id}:done"),
            InlineKeyboardButton("❌ Non completato", callback_data=f"verify:{shift_id}:fail"),
        ]])

        try:
            await context.bot.send_message(
                chat_id=s["telegram_id"],
                text=f"🌙 Ehi *{s['user_name']}*, hai fatto il turno *{s['task_name']}* oggi?",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
            await DatabaseManager.mark_notified(shift_id)
        except Exception as e:
            logger.warning("Impossibile inviare verifica serale all'utente %s: %s", s["telegram_id"], e)

async def build_previous_week_report(today: datetime.date) -> str:
    """Testo del resoconto della settimana (lun-dom) precedente a quella di `today` + classifica generale.

    Condiviso dal job del lunedì e dal comando /report, così i due messaggi
    sono sempre identici.
    """
    monday = today - datetime.timedelta(days=today.weekday() + 7)
    week_shifts = await DatabaseManager.get_shifts_for_week(monday)
    ranking = await DatabaseManager.get_all_time_stats(today)
    trash = await DatabaseManager.get_trash_for_week(monday)
    trash_ranking = await DatabaseManager.get_trash_stats(today)
    return format_weekly_report(monday, week_shifts, ranking, trash, trash_ranking)

async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task del lunedì mattina: resoconto della settimana appena conclusa + classifica generale a tutti i registrati.

    Viene inviato il lunedì successivo (non il sabato) apposta: i turni di
    sabato e domenica devono avere il tempo di essere completati e passare
    dalla verifica serale delle 23:00 prima che il resoconto li includa.
    """
    logger.info("Esecuzione job: resoconto settimanale.")
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    text = await build_previous_week_report(today)

    roommates = await DatabaseManager.get_roommates()
    for r in roommates:
        if not r["telegram_id"]:
            continue
        try:
            await context.bot.send_message(
                chat_id=r["telegram_id"], text=text, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning("Impossibile inviare il resoconto settimanale a %s: %s", r["telegram_id"], e)

# In PTB >= 20 `run_daily(days=...)` usa la numerazione cron 0-6 = domenica-sabato
# (non lunedì-domenica come datetime.weekday()): con 0 i job del "lunedì"
# partivano in realtà la domenica.
MONDAY = 1
SUNDAY = 0

def setup_scheduled_jobs(job_queue) -> None:
    """Configura i task programmati tramite APScheduler / JobQueue di PTB."""
    tz = pytz.timezone(TIMEZONE)

    # Generazione turni: ogni lunedì mattina
    job_queue.run_daily(
        generate_weekly_shifts_job,
        time=datetime.time(hour=7, minute=0, tzinfo=tz),
        days=(MONDAY,),
        name="weekly_shift_generation",
    )

    # Verifica serale: tutti i giorni alle 23:00
    job_queue.run_daily(
        evening_verification_job,
        time=datetime.time(hour=23, minute=0, tzinfo=tz),
        name="evening_verification",
    )

    # Verifica Kosettine: domenica alle 23:00 per i compiti ancora in attesa
    job_queue.run_daily(
        sunday_trash_verification_job,
        time=datetime.time(hour=23, minute=0, tzinfo=tz),
        days=(SUNDAY,),
        name="sunday_trash_verification",
    )

    # Resoconto settimanale: lunedì mattina, sulla settimana appena
    # conclusa (non sabato: i turni di sabato/domenica devono poter essere
    # completati prima che il resoconto venga generato)
    job_queue.run_daily(
        weekly_report_job,
        time=datetime.time(hour=9, minute=0, tzinfo=tz),
        days=(MONDAY,),
        name="weekly_report",
    )

    logger.info(
        "Job schedulati: generazione turni lunedì 07:00, verifica serale ogni giorno 23:00, "
        "resoconto settimanale lunedì 09:00 sulla settimana precedente (%s).",
        TIMEZONE
    )
