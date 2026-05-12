import argparse
from pathlib import Path

from chunk_module import (
    chunk_by_paragraph,
    load_jsonl,
    make_chunk_id_base,
    write_jsonl,
)
from preprocess_module import OUTPUT_DIR


def dedup_rows(rows):
    seen = set()
    deduped = []

    for row in rows:
        dedup_text = (row.get("rag_text") or row.get("text") or "").strip()
        key = (row.get("doc_id"), row.get("source_file"), dedup_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_qna_paragraph_chunks(input_jsonl: Path, output_jsonl: Path, chunk_size: int, overlap: int):
    rows = load_jsonl(input_jsonl)
    rows = dedup_rows(rows)
    out_rows = []

    for idx, row in enumerate(rows):
        text = (row.get("rag_text") or row.get("text") or "").strip()
        if not text:
            continue

        chunks = chunk_by_paragraph(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            continue

        base_id = make_chunk_id_base(row, idx)
        for chunk_index, chunk_text in enumerate(chunks):
            chunk_row = {
                **row,
                "chunk_id": f"{base_id}::{chunk_index}",
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "chunk_strategy": "paragraph",
                "chunk_size": chunk_size,
                "chunk_overlap": overlap,
                "data_type": "qna",
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
