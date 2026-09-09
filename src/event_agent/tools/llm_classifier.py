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
Казахстана, проводит выставки, конференции, лекции и культурно-просветительские мероприятия.

КРИТИЧЕСКИ ВАЖНО: НЕ путай Президентский центр с другими учреждениями УДП, у которых в названии тоже есть
слово "центр" или "Президент" - это РАЗНЫЕ организации:
- Дворец Независимости - НЕ Президентский центр;
- ТРК Президента / Телерадиокомплекс Президента - НЕ Президентский центр;
- Медицинский центр УДП, Национальный госпиталь - НЕ Президентский центр;
- Инженерно-технический центр УДП - НЕ Президентский центр;
- Автохозяйство УДП - НЕ Президентский центр;
- упоминание действующего Президента (Токаева) или мероприятий с его участием САМО ПО СЕБЕ
  не делает статью релевантной ПЦ - это разные сущности.

Сохранять нужно ЛЮБУЮ статью, где точно фигурирует именно Президентский центр (а не другое
учреждение) - будь то главная тема, место проведения мероприятия, или упоминание его
руководства/сотрудников. НЕ считается релевантным, если Президентский центр просто
перечислен в общем списке учреждений УДП без связи с событием статьи.
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


_PC_MENTION_RE = re.compile(r"президентск\w*\s+центр\w*", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _find_pc_mentions(text: str, max_mentions: int = 5) -> List[str]:
    """Находит предложения, где ДОСЛОВНО встречается фраза "Президентский центр" (с вариациями
    окончаний). Используется как жёсткий экстрактивный фильтр перед вызовом LLM: если
    модель не может опереться на реальную цитату из текста, она не должна иметь возможность
    придумать несуществующую связь со статьей.
    """
    if not text:
        return []
    sentences = _SENTENCE_SPLIT_RE.split(text)
    mentions = [s.strip() for s in sentences if _PC_MENTION_RE.search(s)]
    return mentions[:max_mentions]


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

    Сначала ищет ДОСЛОВНЫЕ упоминания фразы "Президентский центр" в тексте (регэксп-поиск,
    без LLM). Если упоминаний нет вообще - возвращает is_relevant_to_pc=False сразу, без обращения
    к LLM: небольшая модель (llama3.1:8b) склонна путать Президентский центр с похожими по названию
    учреждениями УДП (Дворец Независимости, ТРК Президента, Медицинский центр,
    Инженерно-технический центр) и придумывать несуществующую связь. Раз в тексте нет самого
    словосочетания - домысливать нечего.

    Если упоминания найдены - передаёт LLM ТОЛЬКО эти реальные цитаты (плюс полный текст для
    контекста) и просит решить, случайное это упоминание или содержательное.

    Возвращает None, если LLM недоступна (и упоминания были найдены) - вызывающий код в этом
    случае НЕ сохраняет статью.
    """
    title = title or ""
    body_text = body_text or ""
    combined = f"{title}\n{body_text}"

    mentions = _find_pc_mentions(combined)
    if not mentions:
        return TopicDecision(
            is_relevant_to_pc=False,
            reason="Словосочетание 'Президентский центр' дословно не встречается в тексте статьи",
        )

    text_excerpt = body_text[:4000]
    quoted = "\n".join(f'- "{m}"' for m in mentions)

    question = (
        "Вопрос: приведённые выше цитаты - это РЕАЛЬНОЕ, содержательное упоминание Президентского "
        "центра (главная тема, место проведения мероприятия, упоминание его руководства/сотрудников "
        "в контексте их работы там), или СЛУЧАЙНОЕ упоминание (например, Президентский центр просто "
        "перечислен в общем списке учреждений УДП без связи с событием статьи)?\n"
        "is_relevant_to_pc=true ставь, если связь реальная - даже если Президентский центр упомянут "
        "просто как локация.\n"
        "is_relevant_to_pc=false ставь, если это случайное перечисление в списке учреждений.\n"
        "Ответь одним решением с кратким обоснованием, опираясь ТОЛЬКО на приведённые цитаты и "
        "текст статьи ниже - не придумывай связь, которой нет в тексте."
    )
    prompt = (
        _PC_CONTEXT +
        "\nВ статье найдены следующие дословные упоминания 'Президентского центра':\n"
        + quoted +
        "\n\nПолный текст статьи (для контекста):\n"
        f"Заголовок: {title}\n"
        f"Текст: {text_excerpt}\n\n"
        + question
    )

    try:
        llm = _get_llm().with_structured_output(TopicDecision)
        return llm.invoke(prompt)
    except Exception as e:
        log.error("PC topic classification failed (is Ollama running at %s?): %s", settings.ollama_base_url, e)
        return None
