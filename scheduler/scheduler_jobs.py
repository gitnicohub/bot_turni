import logging
import datetime
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import TIMEZONE
from database.db_manager import DatabaseManager
from utils.helpers import format_weekly_report

logger = logging.getLogger(__name__)

async def generate_weekly_shifts_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task settimanale: genera ciclicamente i turni della settimana corrente."""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    monday = today - datetime.timedelta(days=today.weekday())
    await DatabaseManager.ensure_week_shifts(monday)
    logger.info("Turni della settimana generati a partire da %s.", monday)

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

async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task del sabato mattina: resoconto della settimana + classifica generale a tutti i registrati."""
    logger.info("Esecuzione job: resoconto settimanale.")
    tz = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    monday = today - datetime.timedelta(days=today.weekday())

    week_shifts = await DatabaseManager.get_shifts_for_week(monday)
    ranking = await DatabaseManager.get_all_time_stats(today)
    text = format_weekly_report(monday, week_shifts, ranking)

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

def setup_scheduled_jobs(job_queue) -> None:
    """Configura i task programmati tramite APScheduler / JobQueue di PTB."""
    tz = pytz.timezone(TIMEZONE)

    # Generazione turni: ogni lunedì mattina (0 = lunedì per JobQueue.run_daily)
    job_queue.run_daily(
        generate_weekly_shifts_job,
        time=datetime.time(hour=7, minute=0, tzinfo=tz),
        days=(0,),
        name="weekly_shift_generation",
    )

    # Verifica serale: tutti i giorni alle 23:00
    job_queue.run_daily(
        evening_verification_job,
        time=datetime.time(hour=23, minute=0, tzinfo=tz),
        name="evening_verification",
    )

    # Resoconto settimanale: sabato mattina (5 = sabato per JobQueue.run_daily)
    job_queue.run_daily(
        weekly_report_job,
        time=datetime.time(hour=9, minute=0, tzinfo=tz),
        days=(5,),
        name="weekly_report",
    )

    logger.info(
        "Job schedulati: generazione turni lunedì 07:00, verifica serale ogni giorno 23:00, "
        "resoconto settimanale sabato 09:00 (%s).",
        TIMEZONE
    )
