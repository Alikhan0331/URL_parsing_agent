"""Два терминальных узла после classify_topic: keep_record / discard_record.

Если граф вызван с реальным sqlite-соединением (state["conn"], продакшен-режим из
 pipeline.daily_scan) - оба узла также пишут в processed_urls, чтобы инкрементальный обход
не перепроверял эти же ссылки повторно на следующем прогоне. Запись в processed_urls делается
ТОЛЬКО если решение было окончательным (topic_conclusive=True) - если LLM была недоступна
или извлечение не удалось, статья должна быть перепроверена в следующий раз.
"""
import logging
from event_agent.graph.state import CrawlState

log = logging.getLogger(__name__)


def keep_record_node(state: CrawlState) -> dict:
    record = state["current_record"]
    log.info("KEEP (relevant to ПЦ): %s", record.url)

    conn = state.get("conn")
    if conn is not None:
        from event_agent.storage.db import mark_processed, save_article

        site_name = state.get("site_name") or "unknown"
        reason = state.get("topic_reason") or ""
        mark_processed(conn, site_name, record.url, True, reason)
        save_article(conn, site_name, record, [reason])

    return {"all_records": [record], "saved_count": 1}


def discard_record_node(state: CrawlState) -> dict:
    record = state.get("current_record")
    url = record.url if record else "unknown"
    log.info("DISCARD (not relevant to ПЦ - %s): %s", state.get("topic_reason"), url)

    conn = state.get("conn")
    if conn is not None and record is not None and state.get("topic_conclusive"):
        from event_agent.storage.db import mark_processed

        site_name = state.get("site_name") or "unknown"
        mark_processed(conn, site_name, record.url, False, state.get("topic_reason"))

    return {"saved_count": 0}
