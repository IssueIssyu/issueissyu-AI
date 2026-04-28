import argparse
from pathlib import Path

from chunk_module import load_jsonl, make_chunk_id_base, write_jsonl
from preprocess_module import OUTPUT_DIR


def build_tl1_no_split(input_jsonl: Path, output_jsonl: Path):
    rows = load_jsonl(input_jsonl)
    out_rows = []

    for idx, row in enumerate(rows):
        text = (row.get("rag_text") or row.get("text") or "").strip()
        if not text:
            continue

        base_id = make_chunk_id_base(row, idx)
        chunk_row = {
            **row,
            "chunk_id": f"{base_id}::0",
            "chunk_index": 0,
            "chunk_text": text,
            "chunk_strategy": "none",
            "chunk_size": len(text),
            "chunk_overlap": 0,
        }
        out_rows.append(chunk_row)

    write_jsonl(output_jsonl, out_rows)
    print(f"TL1 chunking 완료 (무분할): {output_jsonl}")
    print(f"input_rows={len(rows)}, output_chunks={len(out_rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_DIR / "tl1_rag_documents.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "tl1_chunks_none.jsonl"),
    )
    args = parser.parse_args()

    build_tl1_no_split(
        input_jsonl=Path(args.input),
        output_jsonl=Path(args.output),
    )


if __name__ == "__main__":
    main()
