from __future__ import annotations


def append_source_link_to_pin_content(body: str, source_url: str) -> str:
    """가공 본문 끝에 원문 기사 URL을 붙인다 (중복 방지)."""
    text = (body or "").strip()
    url = (source_url or "").strip()
    if not url or not text:
        return text or url

    if url in text:
        return text

    normalized = url.rstrip("/")
    for line in text.splitlines():
        line = line.strip()
        if line == url or line.rstrip("/") == normalized:
            return text
        if line.startswith("http") and normalized in line:
            return text

    return f"{text}\n\n원문 기사: {url}"
