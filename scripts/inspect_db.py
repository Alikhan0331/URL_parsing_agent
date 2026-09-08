"""Утилита для быстрого просмотра содержимого output/articles.db без sqlite3 CLI.

Использование:
    python scripts/inspect_db.py                 # все записи, кратко
    python scripts/inspect_db.py --site akorda    # только по одному сайту
    python scripts/inspect_db.py --full           # с полным текстом статьи
"""
import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path("output/articles.db")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=None, help="Фильтр по имени сайта из config/sites.json")
    parser.add_argument("--full", action="store_true", help="Показать полный текст статьи")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"База {DB_PATH} ещё не создана - запустите scripts/run_daily.py хотя бы один раз.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM articles"
    params = []
    if args.site:
        query += " WHERE site = ?"
        params.append(args.site)
    query += " ORDER BY discovered_at DESC"

    rows = conn.execute(query, params).fetchall()
    print(f"Всего записей: {len(rows)}\n")

    for row in rows:
        print(f"[{row['site']}] {row['title']}")
        print(f"  url: {row['url']}")
        print(f"  найдено: {row['discovered_at']} | ключевые слова: {row['matched_keywords']}")
        if args.full:
            print(f"  текст: {row['body_text']}")
        print()


if __name__ == "__main__":
    main()
