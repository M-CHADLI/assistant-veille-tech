from __future__ import annotations

from bs4 import BeautifulSoup

from app.ingest import cleaning


def test_clean_html_to_markdown_strips_tags() -> None:
    html = "<article><h1>Titre</h1><p>Para <b>gras</b>.</p></article>"
    md = cleaning.clean_html_to_markdown(html)
    assert "<h1>" not in md
    assert "Titre" in md
    assert "gras" in md


def test_dedupe_removes_duplicate_urls() -> None:
    arts = [
        {"id": "a", "url": "https://x.example/a", "title": "A"},
        {"id": "b", "url": "https://x.example/a", "title": "A bis"},
        {"id": "c", "url": "https://x.example/c", "title": "C"},
    ]
    out = cleaning.dedupe(arts)
    urls = [a["url"] for a in out]
    assert len(urls) == len(set(urls))
    assert len(out) == 2


def test_chunk_splits_long_text() -> None:
    text = "phrase. " * 500
    chunks = cleaning.chunk(text, max_chars=600)
    assert all(len(c) <= 700 for c in chunks)
    assert len(chunks) >= 2


def test_strip_boilerplate_removes_nav_and_footer() -> None:
    html = (
        "<html><body>"
        "<nav>menu</nav>"
        "<main><p>contenu</p></main>"
        "<footer>copyright</footer>"
        "</body></html>"
    )
    soup = cleaning.strip_boilerplate(BeautifulSoup(html, "lxml"))
    text = soup.get_text()
    assert "menu" not in text
    assert "copyright" not in text
    assert "contenu" in text
