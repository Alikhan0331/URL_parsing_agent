"""Долгоживущий процесс планировщика - главная точка входа для Docker.

Запускает run_daily() каждый день в config.schedule_time (по умолчанию 03:00,
таймзона config.timezone). Это и есть "крон" из задачи - реализован через APScheduler,
а не системный cron, чтобы не усложнять Docker-образ отдельным cron-демоном.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from event_agent.config_sites import load_sites_config
from event_agent.pipeline.runner import run_daily
from event_agent.utils.logging import setup_logging

log = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    config = load_sites_config()
    hour, minute = config.schedule_time.split(":")

    scheduler = BlockingScheduler(timezone=config.timezone)
    trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=config.timezone)

    next_run = trigger.get_next_fire_time(None, datetime.now(trigger.timezone))

    scheduler.add_job(
        run_daily,
        trigger=trigger,
        id="daily_scan",
        misfire_grace_time=3600,
    )

    log.info(
        "Scheduler configured - daily scan at %s (%s). Next scheduled run: %s",
        config.schedule_time, config.timezone, next_run,
    )
    log.info("Running one scan now on startup too (so you don't have to wait for the schedule).")
    run_daily()
    scheduler.start()


if __name__ == "__main__":
    main()
