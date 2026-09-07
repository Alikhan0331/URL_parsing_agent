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
    list_root_path: Optional[str]  # напр. "/ru/post/"; если None - вычисляется из base_list_url
    current_page: int
    max_pages: int
    event_urls: List[str]
    all_records: Annotated[List[EventRecord], operator.add]
    stop: bool


class EventTask(TypedDict):
    """Полезная нагрузка для параллельных Send-вызовов на узел extract_event."""
    url: str
