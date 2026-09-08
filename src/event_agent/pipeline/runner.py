"""Оркестрация одного полного суточного прогона по всем сайтам из config/sites.json."""
import logging

from event_agent.config_sites import load_sites_config
from event_agent.pipeline.daily_scan import scan_site_once
from event_agent.storage.db import get_connection

log = logging.getLogger(__name__)


def run_daily(config_path: str = "config/sites.json") -> int:
    """Возвращает общее число новых сохранённых статей за прогон."""
    config = load_sites_config(config_path)

    with get_connection() as conn:
        total_saved = 0
        for site in config.sites:
            try:
                saved = scan_site_once(site, conn)
                total_saved += saved
            except Exception as e:
                log.error("[%s] Daily scan failed: %s", site.name, e)

        if total_saved == 0:
            log.info("No new matching articles found today across all sites - nothing to do")
        else:
            log.info("Daily run complete: %d new articles saved across %d sites", total_saved, len(config.sites))

        return total_saved
