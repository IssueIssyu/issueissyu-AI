import argparse
import json
from pathlib import Path

from preprocess_module import OUTPUT_DIR


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


def split_fixed(text: str, chunk_size: int, overlap: int):
    text = (text or "").strip()
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

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


def split_by_paragraph(text: str, chunk_size: int, overlap: int):
    text = (text or "").strip()
    if not text:
        return []

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
            if overlap > 0 and len(current) > overlap:
                carry = current[-overlap:].strip()
                current = f"{carry}\n{para}" if carry else para
            else:
                current = para

    if current:
        chunks.append(current)

    refined = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            refined.append(chunk)
            continue
        refined.extend(split_fixed(chunk, chunk_size=chunk_size, overlap=overlap))
    return refined


def dedup_rows(rows):
    seen = set()
    deduped = []

    for row in rows:
        key = (row.get("doc_id"), (row.get("text") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_chunk_base_id(row, fallback_idx: int):
    #같은 doc_id가 여러 파일에 존재할 수 있기 때문에 chunk_id 중복을 막기 위해 doc_id와 source_file 이름을 함께 사용한다. 
    doc_id = str(row.get("doc_id", fallback_idx))
    source_file = str(row.get("source_file", ""))
    source_stem = Path(source_file).stem if source_file else f"row{fallback_idx}"
    return f"{doc_id}::{source_stem}"


def build_qna_paragraph_chunks(input_jsonl: Path, output_jsonl: Path, chunk_size: int, overlap: int):
    rows = load_jsonl(input_jsonl)
    rows = dedup_rows(rows)
    out_rows = []

    for idx, row in enumerate(rows):
        text = (row.get("rag_text") or row.get("text") or "").strip()
        if not text:
            continue

        chunks = split_by_paragraph(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            continue

        base_id = build_chunk_base_id(row, idx)
        for chunk_index, chunk_text in enumerate(chunks):
            chunk_row = {
                **row,
                "chunk_id": f"{base_id}::{chunk_index}",
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "chunk_strategy": "paragraph",
                "chunk_size": chunk_size,
                "chunk_overlap": overlap,
            }
            out_rows.append(chunk_row)

    write_jsonl(output_jsonl, out_rows)
    print(f"QnA chunking 완료 (paragraph): {output_jsonl}")
    print(f"input_rows={len(rows)}, output_chunks={len(out_rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_DIR / "qna_rag_documents.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "qna_chunks_paragraph.jsonl"),
    )
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--overlap", type=int, default=180)
    args = parser.parse_args()

    build_qna_paragraph_chunks(
        input_jsonl=Path(args.input),
        output_jsonl=Path(args.output),
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )


if __name__ == "__main__":
    main()
