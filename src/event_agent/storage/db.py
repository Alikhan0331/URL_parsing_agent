"""SQLite-хранилище для найденных статей.

Простая, зависимая только от stdlib база: агент должен автономно заполнять её
новыми статьями, где встречается нужное ключевое слово, и не трогать уже виденные URL.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

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
"""


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_SCHEMA)


@contextmanager
def get_connection(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def url_seen(conn: sqlite3.Connection, url: str) -> bool:
    cur = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
    return cur.fetchone() is not None


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
