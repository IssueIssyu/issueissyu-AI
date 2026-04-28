import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from preprocess_module import OUTPUT_DIR


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def percentile(values, q):
    if not values:
        return 0
    sorted_values = sorted(values)
    idx = int((q / 100) * (len(sorted_values) - 1))
    return sorted_values[idx]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_DIR / "tl1_chunks_none.jsonl"),
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = 0
    empty_chunk_text = 0
    lengths = []
    chunk_id_counter = Counter()
    chunk_strategy_counter = Counter()
    doc_to_indices = defaultdict(list)

    for row in load_jsonl(input_path):
        rows += 1
        chunk_text = (row.get("chunk_text") or "").strip()
        if not chunk_text:
            empty_chunk_text += 1
        lengths.append(len(chunk_text))

        chunk_id = str(row.get("chunk_id", ""))
        chunk_id_counter[chunk_id] += 1
        chunk_strategy_counter[str(row.get("chunk_strategy", ""))] += 1

        if "::" in chunk_id:
            #chunk_id 형식 = {doc_id}::{source}::{chunk_index}
            doc_id = chunk_id.rsplit("::", 1)[0]
        else:
            doc_id = str(row.get("doc_id", ""))
        chunk_index = int(row.get("chunk_index", -1))
        doc_to_indices[doc_id].append(chunk_index)

    duplicate_chunk_id_rows = sum(v - 1 for v in chunk_id_counter.values() if v > 1)
    non_contiguous_docs = 0
    chunks_per_doc = []
    for indices in doc_to_indices.values():
        sorted_indices = sorted(indices)
        chunks_per_doc.append(len(sorted_indices))
        if sorted_indices != list(range(len(sorted_indices))):
            non_contiguous_docs += 1

    small_ratio = sum(1 for n in lengths if n < 200) / len(lengths) if lengths else 0.0
    large_ratio = sum(1 for n in lengths if n > 1200) / len(lengths) if lengths else 0.0

    print(f"[TL1 Chunk Sanity Check] {input_path}")
    print(f"rows={rows}")
    print(f"unique_doc_ids={len(doc_to_indices)}")
    print(f"empty_chunk_text={empty_chunk_text}")
    print(f"duplicate_chunk_id_rows={duplicate_chunk_id_rows}")
    print(f"non_contiguous_docs={non_contiguous_docs}")
    print(f"chunk_strategies={dict(chunk_strategy_counter)}")
    print(
        "chunk_length_stats="
        f"avg:{round(statistics.mean(lengths), 2) if lengths else 0}, "
        f"p50:{percentile(lengths, 50)}, "
        f"p90:{percentile(lengths, 90)}, "
        f"p95:{percentile(lengths, 95)}, "
        f"max:{max(lengths) if lengths else 0}"
    )
    print(f"small_ratio_lt200={round(small_ratio, 4)}")
    print(f"large_ratio_gt1200={round(large_ratio, 4)}")
    print(
        "chunks_per_doc_stats="
        f"p50:{percentile(chunks_per_doc, 50)}, "
        f"p95:{percentile(chunks_per_doc, 95)}, "
        f"max:{max(chunks_per_doc) if chunks_per_doc else 0}"
    )

    # TL1 should be 1 document -> 1 chunk in this pipeline.
    multi_chunk_docs = sum(1 for n in chunks_per_doc if n > 1)
    print(f"multi_chunk_docs={multi_chunk_docs}")


if __name__ == "__main__":
    main()
