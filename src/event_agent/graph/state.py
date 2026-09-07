import operator
from typing import Annotated, List, Optional, TypedDict
from pydantic import BaseModel, Field


class EventRecord(BaseModel):
    url: str
    title: Optional[str] = None
    body_text: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    is_valid: bool = False


class CrawlState(TypedDict):
    base_list_url: str  # напр. "https://qr-pib.kz/ru/post/?page={n}"
    list_root_path: Optional[str]  # опциональный доп. фильтр по разделу сайта
    current_page: int
    max_pages: Optional[int]  # None = без лимита: остановка только когда страница пустая
    event_urls: List[str]
    previous_links: List[str]  # ссылки с предыдущей страницы - для детекции "битой" пагинации
    all_records: Annotated[List[EventRecord], operator.add]
    stop: bool


class EventTask(TypedDict):
    """Полезная нагрузка для параллельных Send-вызовов на узел extract_event."""
    url: str
