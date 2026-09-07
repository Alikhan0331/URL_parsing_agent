import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel
from langchain_ollama import ChatOllama

from event_agent.config import settings
from event_agent.tools.dom_utils import is_in_navigation

log = logging.getLogger(__name__)

_llm = None
_TRAILING_ID_RE = re.compile(r"-\d{3,}/?$")


class ClassifiedLinks(BaseModel):
    content_card_indices: List[int]


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    return _llm


def classify_links_with_llm(html: str, base_url: str, max_candidates: int = 60) -> Optional[List[str]]:
    """Fallback для сайтов, где структурная эвристика (img + заголовок) не сработала.

    Модель смотрит на список ссылок страницы (текст, наличие картинки/времени, признак
    числового ID в конце URL) и решает, какие из них - карточки контента, а какие -
    служебные/навигационные ссылки. Кандидаты предварительно чистятся тем же фильтром
    is_in_navigation, что и в структурной эвристике - иначе модель захлёбывается
    десятками пунктов меню и путает их с реальным контентом.
    """
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)

    candidates = []
    for i, a in enumerate(anchors):
        if is_in_navigation(a):
            continue

        text = a.get_text(" ", strip=True)
        if not text or len(text) < 10:
            continue

        href = urljoin(base_url, a["href"])
        candidates.append({
            "index": i,
            "href": href,
            "has_image": a.find("img") is not None,
            "has_time": a.find("time") is not None,
            "has_trailing_id": bool(_TRAILING_ID_RE.search(href)),
            "text_preview": text[:150],
        })
        if len(candidates) >= max_candidates:
            break

    if not candidates:
        return []

    listing = "\n".join(
        f'{c["index"]}: href="{c["href"]}" image={c["has_image"]} time={c["has_time"]} '
        f'ends_with_numeric_id={c["has_trailing_id"]} text="{c["text_preview"]}"'
        for c in candidates
    )

    prompt = (
        "Ниже приведён список ссылок со страницы сайта в формате "
        "'индекс: href=... image=... time=... ends_with_numeric_id=... text=...'.\n"
        "Определи, какие из них являются карточками контента в списке "
        "(анонс мероприятия, новости или статьи), а какие - служебные или "
        "навигационные ссылки (пункты меню сайта, разделы 'о нас'/'структура'/'документы', "
        "контакты, ссылки на внешние сервисы вроде подачи обращений, ссылки на другие страницы "
        "пагинации).\n"
        "Важная подсказка: у карточек контента URL почти всегда заканчивается числовым ID "
        "(ends_with_numeric_id=True), а у разделов сайта/меню - нет. Заголовок карточки контента "
        "обычно описывает конкретное событие или новость (кто, что сделал, когда), а не общее "
        "название раздела сайта.\n"
        "Верни только индексы ссылок, которые являются карточками контента.\n\n" + listing
    )

    try:
        llm = _get_llm().with_structured_output(ClassifiedLinks)
        result = llm.invoke(prompt)
    except Exception as e:
        log.error("LLM link classification failed (is Ollama running at %s?): %s",
                  settings.ollama_base_url, e)
        return None

    index_to_href = {c["index"]: c["href"] for c in candidates}
    hrefs = [index_to_href[i] for i in result.content_card_indices if i in index_to_href]
    return list(dict.fromkeys(hrefs))
