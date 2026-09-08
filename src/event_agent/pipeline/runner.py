"""Оркестрация одного полного суточного прогона по всем сайтам из config/sites.json."""
import logging

from event_agent.config_sites import load_sites_config
from event_agent.pipeline.daily_scan import scan_site_once
from event_agent.storage.db import get_connection

log = logging.getLogger(__name__)


def run_daily(config_path: str = "config/sites.json") -> int:
    """Возвращает общее число новых сохранённых статей за прогон."""
    config = load_sites_config(config_path)
    log.info("Загружено %d сайтов из %s: %s", len(config.sites), config_path,
              [s.name for s in config.sites])

    with get_connection() as conn:
        total_saved = 0
        per_site_summary = []

        for i, site in enumerate(config.sites, start=1):
            log.info("--- Сайт %d/%d: %s ---", i, len(config.sites), site.name)
            try:
                saved = scan_site_once(site, conn)
                total_saved += saved
                per_site_summary.append((site.name, saved, None))
            except Exception as e:
                log.error("[%s] Daily scan failed: %s", site.name, e)
                per_site_summary.append((site.name, 0, str(e)))

        log.info("========== ИТОГ ПРОГОНА ==========")
        for name, saved, error in per_site_summary:
            status = f"ОШИБКА: {error}" if error else f"сохранено {saved}"
            log.info("  %s -> %s", name, status)
        log.info("Всего новых статей за прогон: %d (по %d сайтам)", total_saved, len(config.sites))
        log.info("===================================")

        return total_saved
