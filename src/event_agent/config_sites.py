"""Конфигурация сайтов для автономного парсинга.

Босс просил: агент должен работать ТОЛЬКО по заданным сайтам, а не по всему интернету.
Список сайтов задаётся здесь через Pydantic-модели и грузится из config/sites.json.

Фильтрация по keywords убрана: ключевое слово может встречаться в статье, которая не
по теме. Вместо этого каждая статья обязательно проверяется LLM на тему
(см. tools/llm_classifier.classify_topic_pc).
"""
import json
from pathlib import Path
from typing import List
from pydantic import BaseModel


class SiteConfig(BaseModel):
    name: str
    base_list_url: str
    list_root_path: str | None = None
    max_pages_per_run: int = 5


class AgentConfig(BaseModel):
    sites: List[SiteConfig]
    schedule_time: str = "03:00"
    timezone: str = "Asia/Almaty"


def load_sites_config(path: str = "config/sites.json") -> AgentConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AgentConfig(**data)
