"""Узел графа: извлекает статью, проверяет её релевантность Президентскому центру и
(в инкрементальном режиме) пишет результат в БД - всё в ОДНОМ узле.

Раньше это было разбито на три отдельных узла (extract_event -> classify_topic ->
keep_record/discard_record), передающих промежуточные данные (current_record,
topic_is_pc, ...) через общие поля состояния графа. Это ломалось при параллельном
fan-out через Send: несколько веток одновременно писали в одни и те же (не-Annotated)
каналы состояния, и LangGraph выдавал INVALID_CONCURRENT_GRAPH_UPDATE ("Can receive only
one value per step"). Теперь вся обработка одной статьи выполняется внутри одного узла
и наружу отдаётся только через Annotated-поля (all_records, saved_count), которые
корректно поддерживают параллельную запись из многих Send-веток.
"""
import logging

from event_agent.graph.state import EventTask
from event_agent.tools.parser import extract_event
from event_agent.tools.llm_classifier import classify_topic_pc

log = logging.getLogger(__name__)


def extract_event_node(payload: EventTask) -> dict:
    url = payload["url"]
    conn = payload.get("conn")
    site_name = payload.get("site_name") or "unknown"

    log.info("Extracting event: %s", url)
    record = extract_event(url)

    if not record.is_valid:
        log.warning("Skipping invalid extraction (will retry next run): %s", url)
        return {}

    decision = classify_topic_pc(record.title, record.body_text)
    if decision is None:
        log.warning("PC relevance classification unavailable (LLM down) for %s - discarding to be safe", url)
        return {}

    if not decision.is_relevant_to_pc:
        log.info("DISCARD (not relevant to ПЦ - %s): %s", decision.reason, url)
        if conn is not None:
            from event_agent.storage.db import mark_processed
            mark_processed(conn, site_name, url, False, decision.reason)
        return {"saved_count": 0}

    log.info("KEEP (relevant to ПЦ): %s", url)
    if conn is not None:
        from event_agent.storage.db import mark_processed, save_article
        mark_processed(conn, site_name, url, True, decision.reason)
        save_article(conn, site_name, record, [decision.reason])

    return {"all_records": [record], "saved_count": 1}
