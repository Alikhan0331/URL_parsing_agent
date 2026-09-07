from event_agent.tools.parser import extract_list_links

CARD_HTML = """
<a href="/ru/p/62729" class="my-4 block border-b flex flex-col md:flex-row items-center">
    <img class="block my-2" src="https://qr-pib.kz/media/cache/thumb/event.jpeg" alt="">
    <div class="border-b w-full md:ml-4">
        <h4 class="my-2 font-extrabold">Премьера второго сезона Silk Way Star состоялась в Китае</h4>
        <time class="text-[#999fab]" datetime="">07.09.2026</time>
        <p class="my-2 text-[#999FAB]">Первый выпуск второго сезона международного музыкального конкурса...</p>
    </div>
</a>
"""

SAMPLE_HTML = f"""
<html><body>
<nav>
    <a href="/ru/about">О нас</a>
    <a href="/ru/p/2312">Госзакупки</a>
</nav>
<div class="list">
    {CARD_HTML}
    <a href="/ru/p/2350" class="my-4 block border-b flex flex-col md:flex-row items-center">
        <img src="/media/cache/thumb/event2.jpeg" alt="">
        <div><h4>Второе мероприятие с длинным названием</h4><time datetime="">06.09.2026</time></div>
    </a>
</div>
<footer><a href="/ru/p/2299">Управляющий делами</a></footer>
</body></html>
"""


def test_extract_list_links_recognizes_card_structure():
    links = extract_list_links(SAMPLE_HTML, "https://qr-pib.kz/ru/post/?page=1")
    assert len(links) == 2
    assert "https://qr-pib.kz/ru/p/62729" in links
    assert "https://qr-pib.kz/ru/p/2350" in links


def test_extract_list_links_excludes_plain_nav_links_with_same_url_pattern():
    links = extract_list_links(SAMPLE_HTML, "https://qr-pib.kz/ru/post/?page=1")
    assert not any("/ru/p/2312" in link or "/ru/p/2299" in link for link in links)
