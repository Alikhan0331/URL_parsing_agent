"""SQLite-хранилище для найденных статей.

Две таблицы:
- articles: только статьи, признанные релевантными (сохраняются для дальнейшего использования).
- processed_urls: ВСЕ URL, когда-либо доведённые до финального решения LLM (и сохранённые,
  и отклонённые) - используется, чтобы не скачивать и не перепроверять одни и те же
  отклонённые статьи повторно на каждом ежедневном прогоне.
"""
import json
import sqlite3
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


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def get_connection(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def url_seen(conn: sqlite3.Connection, url: str) -> bool:
    """Проверяет, сохранена ли статья по этому URL как релевантная (таблица articles)."""
    cur = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
    return cur.fetchone() is not None


def url_processed(conn: sqlite3.Connection, url: str) -> bool:
    """Проверяет, была ли статья по этому URL УЖЕ доведена до финального решения LLM -
    неважно, сохранена она была или отклонена. Используется для инкрементального обхода,
    чтобы не скачивать и не перепроверять уже отклонённые статьи повторно на каждом прогоне.
    """
    cur = conn.execute("SELECT 1 FROM processed_urls WHERE url = ?", (url,))
    return cur.fetchone() is not None


def mark_processed(conn: sqlite3.Connection, site_name: str, url: str, is_relevant: bool,
                    reason: Optional[str]) -> None:
    """Отмечает URL как доведённый до финального решения LLM (сохранён он или нет).

    Не вызывайте эту функцию, если решение не было реально получено (например, LLM была
    недоступна или извлечение статьи не удалось) - такие URL должны быть перепроверены на
    следующем прогоне, а не пропущены навсегда.
    """
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
