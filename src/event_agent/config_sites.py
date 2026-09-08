"""Конфигурация сайтов для автономного парсинга.

Босс просил: агент должен работать ТОЛЬКО по заданным сайтам, а не по всему интернету.
Список сайтов задаётся здесь через Pydantic-модели и грузится из config/sites.json -
чтобы добавить новый сайт, не нужно трогать код, достаточно отредактировать JSON.
"""
import json
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field


class SiteConfig(BaseModel):
    name: str
    base_list_url: str  # напр. "https://qr-pib.kz/ru/post/?page={n}"
    list_root_path: str | None = None
    keywords: List[str] = Field(default_factory=list)  # статья сохраняется, только если упоминает хотя бы одно
    max_pages_per_run: int = 5  # инкрементальный обход - обычно достаточно первых нескольких страниц


class AgentConfig(BaseModel):
    sites: List[SiteConfig]
    schedule_time: str = "03:00"  # HH:MM по локальному времени контейнера
    timezone: str = "Asia/Almaty"


def load_sites_config(path: str = "config/sites.json") -> AgentConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AgentConfig(**data)
