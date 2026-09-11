"""SQLite-хранилище для найденных статей.

Две таблицы:
- articles: только статьи, признанные релевантными (сохраняются для дальнейшего использования).
- processed_urls: ВСЕ URL, когда-либо доведённые до финального решения LLM (и сохранённые,
  и отклонённые) - используется, чтобы не скачивать и не перепроверять одни и те же
  отклонённые статьи повторно на каждом ежедневном прогоне.

ВАЖНО про потоки: узел extract_event графа запускается ПАРАЛЛЕЛЬНО (fan-out через Send) для
каждой ссылки на странице, и LangGraph реально исполняет эти параллельные ветки в разных
потоках. sqlite3.Connection по умолчанию запрещает использование из другого потока, кроме
того, где было создано ("SQLite objects created in a thread can only be used in that same
thread") - поэтому соединение создаётся с check_same_thread=False, а все операции записи
дополнительно защищены общей блокировкой (threading.Lock), чтобы избежать состояния гонки
и ошибок "database is locked" при одновременной записи из нескольких потоков.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from event_agent.graph.state import EventRecord

DB_PATH = Path("output/articles.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY,
    site TEXT NOT NULL,
    title TEXT,
    body_text TEXT,
    images TEXT,
    matched_keywords TEXT,
    discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_urls (
    url TEXT PRIMARY KEY,
    site TEXT NOT NULL,
    is_relevant INTEGER NOT NULL,
    reason TEXT,
    processed_at TEXT NOT NULL
);
"""

_db_lock = threading.Lock()


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def get_connection(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    init_db(db_path)
    # check_same_thread=False: LangGraph выполняет параллельные Send-ветки (extract_event)
    # в разных потоках, поэтому одно и то же соединение неизбежно используется не только
    # из потока, в котором было создано. Реальная сериализация конкурентных операций
    # обеспечивается блокировкой _db_lock в функциях ниже, а не самим sqlite3.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def url_seen(conn: sqlite3.Connection, url: str) -> bool:
    """Проверяет, сохранена ли статья по этому URL как релевантная (таблица articles)."""
    with _db_lock:
        cur = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
        return cur.fetchone() is not None


def url_processed(conn: sqlite3.Connection, url: str) -> bool:
    """Проверяет, была ли статья по этому URL УЖЕ доведена до финального решения LLM -
    неважно, сохранена она была или отклонена. Используется для инкрементального обхода,
    чтобы не скачивать и не перепроверять уже отклонённые статьи повторно на каждом прогоне.
    """
    with _db_lock:
        cur = conn.execute("SELECT 1 FROM processed_urls WHERE url = ?", (url,))
        return cur.fetchone() is not None


def mark_processed(conn: sqlite3.Connection, site_name: str, url: str, is_relevant: bool,
                    reason: Optional[str]) -> None:
    """Отмечает URL как доведённый до финального решения LLM (сохранён он или нет).

    Не вызывайте эту функцию, если решение не было реально получено (например, LLM была
    недоступна или извлечение статьи не удалось) - такие URL должны быть перепроверены на
    следующем прогоне, а не пропущены навсегда.
    """
    with _db_lock:
        conn.execute(
            "INSERT OR REPLACE INTO processed_urls (url, site, is_relevant, reason, processed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                url,
                site_name,
                1 if is_relevant else 0,
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def save_article(conn: sqlite3.Connection, site_name: str, record: EventRecord, matched_keywords: list[str]) -> None:
    with _db_lock:
        conn.execute(
            "INSERT OR IGNORE INTO articles (url, site, title, body_text, images, matched_keywords, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.url,
                site_name,
                record.title,
                record.body_text,
                json.dumps(record.images, ensure_ascii=False),
                json.dumps(matched_keywords, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
