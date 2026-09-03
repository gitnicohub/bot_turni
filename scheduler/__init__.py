"""Package per la pianificazione dei task con APScheduler / JobQueue."""
from .scheduler_jobs import (
    generate_weekly_shifts_job,
    evening_verification_job,
    weekly_report_job,
    setup_scheduled_jobs,
)

__all__ = [
    "generate_weekly_shifts_job",
    "evening_verification_job",
    "weekly_report_job",
    "setup_scheduled_jobs",
]
