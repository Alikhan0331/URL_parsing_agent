import json
import logging
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama

from event_agent.config import settings
from event_agent.tools.dom_utils import is_in_navigation

log = logging.getLogger(__name__)

_llm = None
_TRAILING_ID_RE = re.compile(r"-\d{3,}/?$")
_BATCH_SIZE = 10

_FEW_SHOT_EXAMPLES = """
Примеры правильной классификации (ориентируйся на них):

0: href="https://www.akorda.kz/ru/glava-gosudarstva-prinyal-ministra-ekologii-483750" image=False time=False ends_with_numeric_id=True text="Глава государства принял министра экологии и природных ресурсов Алибека Куантырова"
-> is_content_card=true, reason="Конкретное событие, URL заканчивается числовым ID"

1: href="https://www.akorda.kz/ru/legal_acts" image=False time=False ends_with_numeric_id=False text="Правовые акты"
-> is_content_card=false, reason="Общее название раздела сайта, нет числового ID"

2: href="https://www.ektu.kz/newsevents/dombra_kuni.aspx" image=False time=False ends_with_numeric_id=False text="Домбыра күні құтты болсын!"
-> is_content_card=true, reason="Поздравление - валидный контент, даже без числового ID"

3: href="https://eotinish.kz/sendAppeal?orgId=77" image=False time=False ends_with_numeric_id=False text="Подать обращение"
-> is_content_card=false, reason="Ссылка на внешний сервис, а не на новость/статью"

4: href="https://www.akorda.kz/ru/executive_office/schedule" image=False time=False ends_with_numeric_id=False text="График приёма граждан"
-> is_content_card=false, reason="Служебная страница раздела сайта, не конкретная новость"
"""

_PC_CONTEXT = """
Президентский центр Республики Казахстан (ПЦ) - многофункциональный музейно-архивно-библиотечный
комплекс в Астане (ул. Алихана Бокейхана, 1а), созданный в 2023 году на базе Библиотеки
Первого Президента РК, в ведении Управления делами Президента (УДП). ПЦ занимается
сохранением, изучением и продвижением исторического наследия Президента и экс-президентов
Казахстана: хранит их личные библиотеки, архивы и музейные собрания, проводит выставки,
конференции, лекции и культурно-просветительские мероприятия, посвящённые истории
независимого Казахстана и институту президентства.

ВАЖНО: сохранять нужно ЛЮБУЮ статью, релевантную ПЦ - не только те, где ПЦ является
главной темой. Считается релевантным, например:
- статья непосредственно о деятельности/истории/коллекциях ПЦ;
- мероприятие (выставка, конференция, встреча, лекция) фактически проходит/прошло в ПЦ,
  даже если организатор - другое ведомство (то есть ПЦ упомянут просто как локация - это
  ВСЁ РАВНО считается релевантным и статью НУЖНО сохранить);
- упоминание руководства/сотрудников ПЦ в контексте их работы в ПЦ.

НЕ считается релевантным только тогда, когда связь с ПЦ случайная/ошибочная:
например, ПЦ просто перечислен в общем списке учреждений УДП без какой-либо связи с
событием статьи, или название совпало с другим учреждением (например, Медицинский центр
УДП - это другое учреждение, а НЕ ПЦ).
"""


class LinkDecision(BaseModel):
    index: int
    is_content_card: bool
    reason: str = Field(description="Краткое объяснение ИМЕННО для этой ссылки")


class ClassifiedLinks(BaseModel):
    decisions: List[LinkDecision]


class TopicDecision(BaseModel):
    is_relevant_to_pc: bool
    reason: str = Field(description="Краткое объяснение, какая связь статьи с ПЦ или почему связи нет")


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0.2)
    return _llm


def _save_debug_decisions(decisions: List[dict], page_hint: str) -> None:
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_hint = "".join(c if c.isalnum() else "_" for c in page_hint)[:80]
    path = debug_dir / f"llm_decisions_{safe_hint}.json"
    path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved LLM reasoning for this page to %s", path)


def _classify_batch(candidates: list[dict]) -> Optional[List[LinkDecision]]:
    listing = "\n".join(
        f'{c["index"]}: href="{c["href"]}" image={c["has_image"]} time={c["has_time"]} '
        f'ends_with_numeric_id={c["has_trailing_id"]} text="{c["text_preview"]}"'
        for c in candidates
    )

    prompt = (
        "Ниже приведён список ссылок со страницы сайта в формате "
        "'индекс: href=... image=... time=... ends_with_numeric_id=... text=...'.\n"
        "Для КАЖДОЙ ссылки реши, является ли она карточкой контента в списке "
        "(отдельная новость, объявление, поздравление, анонс мероприятия или статья), или служебной/навигационной ссылкой.\n"
        "Важно: поздравления, объявления и короткие новости - валидный контент.\n"
        "У карточек контента URL часто заканчивается числовым ID.\n"
        + _FEW_SHOT_EXAMPLES +
        "\nПроанализируй каждую ссылку ИНДИВИДУАЛЬНО.\n"
        "Верни решение по каждому индексу из списка НИЖЕ.\n\n" + listing
    )

    try:
        llm = _get_llm().with_structured_output(ClassifiedLinks)
        result = llm.invoke(prompt)
        return result.decisions
    except Exception as e:
        log.error("LLM link classification failed: %s", e)
        return None


def classify_links_with_llm(html: str, base_url: str, max_candidates: int = 60) -> Optional[List[str]]:
    """Fallback для сайтов, где структурная эвристика не сработала."""
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

    index_to_candidate = {c["index"]: c for c in candidates}
    debug_records = []
    accepted_hrefs = []
    any_batch_succeeded = False

    for start in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[start:start + _BATCH_SIZE]
        decisions = _classify_batch(batch)
        if decisions is None:
            continue
        any_batch_succeeded = True
        for decision in decisions:
            candidate = index_to_candidate.get(decision.index)
            if candidate is None:
                continue
            record = {
                "href": candidate["href"],
                "text_preview": candidate["text_preview"],
                "is_content_card": decision.is_content_card,
                "reason": decision.reason,
            }
            debug_records.append(record)
            log.info("LLM decision: %s -> %s | %s",
                      "ACCEPT" if decision.is_content_card else "reject", candidate["href"], decision.reason)
            if decision.is_content_card:
                accepted_hrefs.append(candidate["href"])

    _save_debug_decisions(debug_records, base_url)

    if not any_batch_succeeded:
        return None

    return list(dict.fromkeys(accepted_hrefs))


def verify_candidates_with_llm(html: str, base_url: str, candidate_hrefs: list[str]) -> Optional[List[str]]:
    """Проверяет ссылки, которые УЖЕ нашёл структурный фильтр."""
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    href_set = set(candidate_hrefs)

    candidates = []
    for i, a in enumerate(anchors):
        href = urljoin(base_url, a["href"])
        if href not in href_set:
            continue
        text = a.get_text(" ", strip=True)
        candidates.append({
            "index": i,
            "href": href,
            "has_image": a.find("img") is not None,
            "has_time": a.find("time") is not None,
            "has_trailing_id": bool(_TRAILING_ID_RE.search(href)),
            "text_preview": text[:150] if text else "",
        })

    if not candidates:
        return list(candidate_hrefs)

    index_to_candidate = {c["index"]: c for c in candidates}
    debug_records = []
    accepted_hrefs = []
    any_batch_succeeded = False

    for start in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[start:start + _BATCH_SIZE]
        decisions = _classify_batch(batch)
        if decisions is None:
            continue
        any_batch_succeeded = True
        for decision in decisions:
            candidate = index_to_candidate.get(decision.index)
            if candidate is None:
                continue
            record = {
                "href": candidate["href"],
                "text_preview": candidate["text_preview"],
                "is_content_card": decision.is_content_card,
                "reason": decision.reason,
            }
            debug_records.append(record)
            log.info("LLM verification: %s -> %s | %s",
                      "CONFIRM" if decision.is_content_card else "REJECT", candidate["href"], decision.reason)
            if decision.is_content_card:
                accepted_hrefs.append(candidate["href"])

    _save_debug_decisions(debug_records, base_url + "_verify")

    if not any_batch_succeeded:
        return None

    return list(dict.fromkeys(accepted_hrefs))


def classify_topic_pc(title: str | None, body_text: str | None) -> Optional[TopicDecision]:
    """Определяет, релевантна ли статья Президентскому центру (ПЦ).

    Сохраняем всё, что реально связано с ПЦ - не только статьи, где он главная тема,
    но и те, где ПЦ выступает как локация мероприятия или упомянут в связи со своей
    деятельностью. Не сохраняем только то, где связь с ПЦ случайная/ошибочная.

    Возвращает None, если LLM недоступна - вызывающий код в этом случае НЕ сохраняет статью.
    """
    text_excerpt = (body_text or "")[:4000]
    question = (
        "Вопрос: есть ли у этой статьи РЕАЛЬНАЯ связь с Президентским центром? Это может быть "
        "главная тема, или ПЦ как место проведения мероприятия, или упоминание его руководства/"
        "сотрудников в контексте их работы там. Отвечай is_relevant_to_pc=true в любом из этих "
        "случаев, даже если ПЦ упомянут как простая локация.\n"
        "is_relevant_to_pc=false ставь ТОЛЬКО если связь случайная или ошибочная - например, ПЦ "
        "просто перечислен в общем списке учреждений без связи с событием статьи, или речь идёт "
        "о совсем другом учреждении с похожим названием.\n"
        "Ответь одним решением с кратким обоснованием."
    )
    prompt = (
        _PC_CONTEXT +
        "\nВот статья для оценки:\n"
        f"Заголовок: {title or ''}\n"
        f"Текст: {text_excerpt}\n\n"
        + question
    )

    try:
        llm = _get_llm().with_structured_output(TopicDecision)
        return llm.invoke(prompt)
    except Exception as e:
        log.error("PC topic classification failed (is Ollama running at %s?): %s", settings.ollama_base_url, e)
        return None
