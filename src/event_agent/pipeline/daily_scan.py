"""Инкрементальный автономный обход одного сайта.

Это ТОНКАЯ ОБЁРТКА над LangGraph-графом (event_agent.graph.builder.build_graph) - единой
реализацией логики обхода, которую используют и продакшен-планировщик (через этот модуль),
и ручной разовый прогон (scripts/run_crawl.py). Раньше здесь была отдельная процедурная
копия почти того же самого пайплайна (list_page -> verify -> extract -> classify_topic -> save),
из-за чего каждый фикс приходилось переносить в оба места вручную - и один раз это
забыли сделать сразу. Теперь есть только одна реализация; разница между вызовами -
только в том, передаётся ли sqlite-соединение (state["conn"]): если да, граф сам фильтрует
уже обработанные ссылки (processed_urls) и сохраняет релевантные статьи в БД.
"""
import logging
import sqlite3

from event_agent.config_sites import SiteConfig
from event_agent.graph.builder import build_graph

log = logging.getLogger(__name__)

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def scan_site_once(site: SiteConfig, conn: sqlite3.Connection) -> int:
    """Возвращает количество НОВЫХ сохранённых статей за этот запуск."""
    log.info("=== [%s] Начинаю обход (обязательная проверка на релевантность ПЦ) ===", site.name)

    max_pages = site.max_pages_per_run
    recursion_limit = (max_pages + 1) * 6  # с запасом на classify_topic/keep_record/discard_record узлы

    result = _get_graph().invoke(
        {
            "base_list_url": site.base_list_url,
            "list_root_path": site.list_root_path,
            "current_page": 1,
            "max_pages": max_pages,
            "last_page": False,
            "event_urls": [],
            "previous_links": [],
            "all_records": [],
            "saved_count": 0,
            "stop": False,
            "conn": conn,
            "site_name": site.name,
        },
        config={"recursion_limit": recursion_limit},
    )

    saved_count = result.get("saved_count", 0)
    log.info("=== [%s] Обход завершён: сохранено %d новых статей ===", site.name, saved_count)
    return saved_count
