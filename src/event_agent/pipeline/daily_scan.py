"""Инкрементальный автономный обход одного сайта.

В отличие от scripts/run_crawl.py (разовый ручной прогон с --max-pages), этот модуль
предназначен для регулярного (крон/scheduler) запуска: он останавливается, как только
встречает URL, который уже есть в базе - потому что списки новостей обычно отсортированы
от новых к старым, и если текущий URL уже видели, то дальше пойдут ещё более старые статьи.

Если у сайта keywords пуст ([]) - фильтр по ключевым словам отключён, сохраняются ВСЕ
валидные статьи. Если keywords заданы - сохраняются только статьи, где встречается
хотя бы одно из них.
"""
import logging
import sqlite3

from event_agent.config_sites import SiteConfig
from event_agent.storage.db import url_seen, save_article
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.parser import extract_list_links, extract_event
from event_agent.tools.llm_classifier import classify_links_with_llm
from event_agent.config import settings

log = logging.getLogger(__name__)

_NO_FILTER_MARKER = "*"


def _find_matched_keywords(record, keywords: list[str]) -> list[str]:
    if not keywords:
        return [_NO_FILTER_MARKER]

    haystack = f"{record.title or ''} {record.body_text or ''}".lower()
    return [kw for kw in keywords if kw.lower() in haystack]


def scan_site_once(site: SiteConfig, conn: sqlite3.Connection) -> int:
    """Возвращает количество НОВЫХ сохранённых статей за этот запуск."""
    saved_count = 0
    filter_note = "БЕЗ ФИЛЬТРА (keywords пуст - сохраняем всё)" if not site.keywords else f"фильтр: {site.keywords}"
    log.info("=== [%s] Начинаю обход (%s) ===", site.name, filter_note)

    for page_num in range(1, site.max_pages_per_run + 1):
        url = site.base_list_url.format(n=page_num)
        log.info("[%s] Fetching list page: %s", site.name, url)

        html = fetch_html(url)
        links = extract_list_links(html, url, list_root_path=site.list_root_path) if html else []

        if not links:
            html = fetch_html(url, force_browser=True)
            links = extract_list_links(html, url, list_root_path=site.list_root_path) if html else []

        if not links and html and settings.use_llm_fallback:
            llm_links = classify_links_with_llm(html, url)
            links = llm_links or []

        if not links:
            log.info("[%s] No links on page %d, stopping this site for today", site.name, page_num)
            break

        new_links = [link for link in links if not url_seen(conn, link)]
        if not new_links:
            log.info(
                "[%s] All %d links on page %d are already known - stopping "
                "(reached previously-seen content)", site.name, len(links), page_num,
            )
            break

        for link in new_links:
            record = extract_event(link)
            if not record.is_valid:
                log.warning("[%s] Skipping invalid extraction: %s", site.name, link)
                continue

            matched = _find_matched_keywords(record, site.keywords)
            if matched:
                save_article(conn, site.name, record, matched)
                saved_count += 1
                if matched == [_NO_FILTER_MARKER]:
                    log.info("[%s] SAVED (no filter): %s", site.name, link)
                else:
                    log.info("[%s] SAVED (matched %s): %s", site.name, matched, link)
            else:
                log.info("[%s] Not saved (no keyword match): %s", site.name, link)

        if len(new_links) < len(links):
            log.info("[%s] Reached previously-seen content mid-page, stopping", site.name)
            break

    log.info("=== [%s] Обход завершён: сохранено %d новых статей ===", site.name, saved_count)
    return saved_count
