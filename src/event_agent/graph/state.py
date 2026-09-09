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
    base_list_url: str
    list_root_path: Optional[str]
    current_page: int
    max_pages: Optional[int]
    event_urls: List[str]
    previous_links: List[str]
    current_record: Optional[EventRecord]
    topic_is_pc: Optional[bool]
    topic_reason: Optional[str]
    all_records: Annotated[List[EventRecord], operator.add]
    stop: bool


class EventTask(TypedDict):
    """Полезная нагрузка для параллельных Send-вызовов на узел extract_event."""
    url: str
