import hashlib
import json
import re
from pathlib import Path


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def check_chunk_params(chunk_size: int, overlap: int):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")


def _make_overlap_text(text: str, overlap: int):
    if overlap <= 0:
        return ""
    if len(text) <= overlap:
        return text.strip()

    tail = text[-overlap:]

    sentence_breaks = [m.end() for m in re.finditer(r"[.!?]\s+|\n+", tail)]
    if sentence_breaks:
        return tail[sentence_breaks[-1]:].strip()

    ws_idx = max(tail.rfind(" "), tail.rfind("\n"), tail.rfind("\t"))
    if ws_idx != -1:
        return tail[ws_idx + 1:].strip()

    return tail.strip()


def chunk_fixed(text: str, chunk_size: int, overlap: int):
    text = (text or "").strip()
    if not text:
        return []
    check_chunk_params(chunk_size=chunk_size, overlap=overlap)

    chunks = []
    step = chunk_size - overlap
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


def chunk_by_paragraph(text: str, chunk_size: int, overlap: int):
    text = (text or "").strip()
    if not text:
        return []
    check_chunk_params(chunk_size=chunk_size, overlap=overlap)

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current = ""

    for para in paragraphs:
        if not current:
            current = para
            continue

        merged = f"{current}\n{para}"
        if len(merged) <= chunk_size:
            current = merged
        else:
            chunks.append(current)
            carry = _make_overlap_text(current, overlap)
            current = f"{carry}\n{para}" if carry else para

    if current:
        chunks.append(current)

    refined = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            refined.append(chunk)
            continue
        refined.extend(chunk_fixed(chunk, chunk_size=chunk_size, overlap=overlap))
    return refined


def make_chunk_id_base(row, fallback_idx: int):
    doc_id = str(row.get("doc_id", fallback_idx))
    source_file = str(row.get("source_file", ""))
    if not source_file:
        return f"{doc_id}::row{fallback_idx}"

    source_path = Path(source_file)
    source_slug = source_path.stem
    source_key = str(row.get("source_path") or source_file)
    source_hash = hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}::{source_slug}_{source_hash}"
