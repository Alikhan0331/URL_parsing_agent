# URL Parsing Agent

Универсальный агент на LangGraph, который обходит сайты со списком материалов (пагинация вида `?page=N`),
находит карточки-мероприятия/статьи и вытаскивает из каждой заголовок, основной текст и изображения.
Извлечённые данные сохраняются в JSON. Запись в Odoo вынесена в отдельный, ещё не подключённый модуль
(`src/event_agent/tools/odoo_client.py`) — сделано намеренно, чтобы сначала проверять качество парсинга.

## Как это работает

1. `list_page` узел скачивает страницу списка (с fallback на headless-браузер, если сайт JS-based)
   и находит ссылки на карточки по частоте паттерна URL (без хардкода под конкретный сайт).
2. Через `Send` API LangGraph все найденные ссылки со страницы обрабатываются параллельно узлом
   `extract_event`, который вытаскивает title / og:image / основной текст (через `trafilatura`).
3. `pagination` узел решает: переходить ли на следующую страницу или остановиться (пустая страница /
   лимит `max_pages`).
4. Итоговые записи копятся в `state.all_records` и сохраняются в `output/events.json`.

## Структура проекта

```
src/event_agent/
├── config.py            # env-переменные и константы
├── graph/
│   ├── state.py          # CrawlState, EventRecord
│   ├── builder.py        # сборка StateGraph
│   └── router.py         # функции-роутеры (conditional edges)
├── nodes/
│   ├── list_page.py
│   ├── extract_event.py
│   └── pagination.py
├── tools/
│   ├── fetcher.py         # HTTP + Playwright fallback
│   ├── parser.py          # извлечение ссылок / контента
│   └── odoo_client.py     # заготовка для будущей записи в Odoo (не используется пока)
└── utils/
    ├── logging.py
    └── retry.py
scripts/run_crawl.py       # точка входа CLI
tests/
docker/
```

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env

python scripts/run_crawl.py --base-url "https://qr-pib.kz/ru/post/?page={n}" --max-pages 3
```

Результат появится в `output/events.json`.

## Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Тесты

```bash
pytest tests/unit
```

## Roadmap

- [x] Обход пагинации и извлечение карточек
- [x] Извлечение title / текст / картинки с fallback на headless-браузер
- [ ] Валидация записей через LLM (фильтр мусора)
- [ ] Запись в Odoo через XML-RPC (`tools/odoo_client.py`)
- [ ] Дедупликация по `source_url` перед записью
