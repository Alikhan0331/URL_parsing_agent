import logging
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel
from langchain_ollama import ChatOllama

from event_agent.config import settings

log = logging.getLogger(__name__)

_llm = None


class ClassifiedLinks(BaseModel):
    content_card_indices: List[int]


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    return _llm


def classify_links_with_llm(html: str, base_url: str, max_candidates: int = 60) -> Optional[List[str]]:
    """Fallback для сайтов, где структурная эвристика (img + заголовок) не сработала.

    Вместо жёстких правил модель сама смотрит на список ссылок страницы (текст, наличие
    картинки/времени) и решает, какие из них - карточки контента (мероприятия/новости/статьи),
    а какие - служебные/навигационные ссылки. Это то же самое рассуждение, которое можно
    провести вручную, глядя на HTML, только выполняемое моделью автоматически на любом сайте.

    Возвращает None, если LLM недоступна или классификация не удалась (чтобы вызывающий код
    мог отличить "ничего не нашли" от "LLM не смогла ответить").
    """
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)

    candidates = []
    for i, a in enumerate(anchors):
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 10:
            continue
        candidates.append({
            "index": i,
            "href": urljoin(base_url, a["href"]),
            "has_image": a.find("img") is not None,
            "has_time": a.find("time") is not None,
            "text_preview": text[:150],
        })
        if len(candidates) >= max_candidates:
            break

    if not candidates:
        return []

    listing = "\n".join(
        f'{c["index"]}: href="{c["href"]}" image={c["has_image"]} time={c["has_time"]} text="{c["text_preview"]}"'
        for c in candidates
    )

    prompt = (
        "Ниже приведён список ссылок со страницы сайта в формате "
        "'индекс: href=... image=... time=... text=...'.\n"
        "Определи, какие из них являются карточками контента в списке "
        "(анонс мероприятия, новости или статьи), а какие - служебные или "
        "навигационные ссылки (меню, футер, контакты, госзакупки, страницы о руководстве и т.п.).\n"
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
