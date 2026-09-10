"""Инкрементальный автономный обход одного сайта.

ФИЛЬТРАЦИЯ ПО ТЕМЕ: статья сохраняется, если она РЕЛЕВАНТНА Президентскому центру (ПЦ) -
включая случаи, когда ПЦ упомянут просто как локация мероприятия. Ключевые слова больше
НЕ используются - вместо них каждая статья отправляется LLM (classify_topic_pc).

ИНКРЕМЕНТАЛЬНОСТЬ: инкрементальный обход останавливается, как только встречает URL, который
уже был доведён до финального решения LLM (processed_urls) - неважно, сохранён он был или
отклонён. Раньше "уже виденными" считались только СОХРАНЁННЫЕ статьи, из-за чего каждый
день заново скачивались и заново прогонялись через LLM одни и те же отклонённые статьи - теперь
это не повторяется.

Структурный фильтр кандидатов обязательно проверяется LLM (verify_candidates_with_llm)
перед извлечением, если включён флаг LLM_VERIFY_STRUCTURAL.
"""
import logging
import sqlite3

from event_agent.config_sites import SiteConfig
from event_agent.storage.db import url_processed, mark_processed, save_article
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.parser import extract_list_links, extract_event
from event_agent.tools.llm_classifier import classify_links_with_llm, verify_candidates_with_llm, classify_topic_pc
from event_agent.config import settings

log = logging.getLogger(__name__)


def scan_site_once(site: SiteConfig, conn: sqlite3.Connection) -> int:
    """Возвращает количество НОВЫХ сохранённых статей за этот запуск."""
    saved_count = 0
    log.info("=== [%s] Начинаю обход (обязательная проверка на релевантность ПЦ) ===", site.name)

    for page_num in range(1, site.max_pages_per_run + 1):
        url = site.base_list_url.format(n=page_num)
        log.info("[%s] Fetching list page: %s", site.name, url)

        html = fetch_html(url)
        links = extract_list_links(html, url, list_root_path=site.list_root_path) if html else []

        if not links:
            html = fetch_html(url, force_browser=True)
            links = extract_list_links(html, url, list_root_path=site.list_root_path) if html else []

        if links and html and settings.llm_verify_structural:
            log.info("[%s] Verifying %d structurally-matched link(s) on page %d with LLM",
                      site.name, len(links), page_num)
            verified = verify_candidates_with_llm(html, url, links)
            if verified is not None:
                rejected = set(links) - set(verified)
                if rejected:
                    log.info(
                        "[%s] LLM verification rejected %d structurally-matched link(s) on page %d: %s",
                        site.name, len(rejected), page_num, sorted(rejected),
                    )
                links = verified
            else:
                log.warning(
                    "[%s] LLM verification unavailable (Ollama unreachable?) - keeping "
                    "structurally-matched links unverified for page %d", site.name, page_num,
                )

        if not links and html and settings.use_llm_fallback:
            llm_links = classify_links_with_llm(html, url)
            links = llm_links or []

        if not links:
            log.info("[%s] No links on page %d, stopping this site for today", site.name, page_num)
            break

        new_links = [link for link in links if not url_processed(conn, link)]
        if not new_links:
            log.info(
                "[%s] All %d links on page %d are already processed - stopping "
                "(reached previously-processed content)", site.name, len(links), page_num,
            )
            break

        for link in new_links:
            record = extract_event(link)
            if not record.is_valid:
                log.warning("[%s] Skipping invalid extraction (will retry next run): %s", site.name, link)
                continue

            topic_decision = classify_topic_pc(record.title, record.body_text)
            if topic_decision is None:
                log.warning(
                    "[%s] PC relevance check unavailable (LLM down) - skipping to be safe, "
                    "will retry next run: %s", site.name, link,
                )
                continue

            mark_processed(conn, site.name, link, topic_decision.is_relevant_to_pc, topic_decision.reason)

            if not topic_decision.is_relevant_to_pc:
                log.info("[%s] Not saved (not relevant to \u041f\u0426 - %s): %s", site.name, topic_decision.reason, link)
                continue

            save_article(conn, site.name, record, [topic_decision.reason])
            saved_count += 1
            log.info("[%s] SAVED (relevant to \u041f\u0426 - %s): %s", site.name, topic_decision.reason, link)

        if len(new_links) < len(links):
            log.info("[%s] Reached previously-processed content mid-page, stopping", site.name)
            break

    log.info("=== [%s] Обход завершён: сохранено %d новых статей ===", site.name, saved_count)
    return saved_count
