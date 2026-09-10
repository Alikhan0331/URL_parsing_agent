import operator
from typing import Annotated, Any, List, Optional, TypedDict
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
    last_page: bool
    event_urls: List[str]
    previous_links: List[str]
    all_records: Annotated[List[EventRecord], operator.add]
    saved_count: Annotated[int, operator.add]
    stop: bool
    conn: Optional[Any]
    site_name: Optional[str]


class EventTask(TypedDict):
    """Полезная нагрузка для параллельных Send-вызовов на узел extract_event.

    ВАЖНО: extract_event запускается параллельно (fan-out через Send) для каждой ссылки
    на странице. Поэтому conn/site_name передаются ЗДЕСЬ, в самой задаче, а не читаются
    из общего состояния - общие (не-Annotated) поля state нельзя перезаписывать параллельно
    из нескольких Send-веток одновременно (LangGraph выдаст INVALID_CONCURRENT_GRAPH_UPDATE).
    Вся обработка одной статьи (извлечение + проверка релевантности + запись в БД)
    поэтому выполняется целиком внутри extract_event_node, а не размазана по нескольким узлам
    с общими промежуточными полями.
    """
    url: str
    conn: Optional[Any]
    site_name: Optional[str]
