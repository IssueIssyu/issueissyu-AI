import argparse
import json
import statistics
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

    # 너무 큰 문단 있을 경우
    refined = []
    for c in chunks:
        if len(c) <= chunk_size:
            refined.append(c)
            continue
        refined.extend(split_fixed(c, chunk_size=chunk_size, overlap=overlap))
    return refined


def tokenize_estimate(text: str):
    # 경험적 추정 (글자 수를 2로 나누면 대략적인 토큰 수)
    return max(1, len(text) // 2)


def evaluate_chunks(chunks):
    if not chunks:
        return {
            "chunk_count": 0,
            "average_chars": 0,
            "95p_chars": 0,
            "average_tokens_estimate": 0,
            "95p_tokens_estimate": 0,
            "lessthan_200_ratio": 0.0,
            "greaterthan_1200_ratio": 0.0,
        }

    char_lengths = [len(c) for c in chunks]
    token_lengths = [tokenize_estimate(c) for c in chunks]

    too_small = sum(1 for n in char_lengths if n < 200)
    too_large = sum(1 for n in char_lengths if n > 1200)

    return {
        "chunk_count": len(chunks),
        "average_chars": round(statistics.mean(char_lengths), 2),
        "95p_chars": percentile(char_lengths, 95),
        "average_tokens_estimate": round(statistics.mean(token_lengths), 2),
        "95p_tokens_estimate": percentile(token_lengths, 95),
        "lessthan_200_ratio": round(too_small / len(chunks), 4),
        "greaterthan_1200_ratio": round(too_large / len(chunks), 4),
    }


def percentile(values, q):
    if not values:
        return 0
    s = sorted(values)
    idx = int((q / 100) * (len(s) - 1))
    return s[idx]


def build_chunks(rows, strategy: str, chunk_size: int, overlap: int):
    all_chunks = []
    for row in rows:
        text = row.get("rag_text") or row.get("text") or ""
        if strategy == "fixed":
            chunks = split_fixed(text, chunk_size=chunk_size, overlap=overlap)
        elif strategy == "paragraph":
            chunks = split_by_paragraph(text, chunk_size=chunk_size, overlap=overlap)
        else:
            raise ValueError(f"unsupported strategy: {strategy}")
        all_chunks.extend(chunks)
    return all_chunks


def run_experiment(input_jsonl: Path, output_report: Path):
    rows = load_jsonl(input_jsonl)
    configs = [
        {"name": "fixed_600_100", "strategy": "fixed", "chunk_size": 600, "overlap": 100},
        {"name": "fixed_900_150", "strategy": "fixed", "chunk_size": 900, "overlap": 150},
        {"name": "paragraph_700_120", "strategy": "paragraph", "chunk_size": 700, "overlap": 120},
        {"name": "paragraph_1000_150", "strategy": "paragraph", "chunk_size": 1000, "overlap": 150},
    ]

    result_rows = []
    for cfg in configs:
        chunks = build_chunks(
            rows,
            strategy=cfg["strategy"],
            chunk_size=cfg["chunk_size"],
            overlap=cfg["overlap"],
        )
        metrics = evaluate_chunks(chunks)
        result_rows.append({**cfg, **metrics})

    report = {
        "input_file": str(input_jsonl),
        "document_count": len(rows),
        "experiments": result_rows,
    }

    output_report.parent.mkdir(parents=True, exist_ok=True)
    with output_report.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"chunk 실험 완료: {output_report}")
    for row in result_rows:
        print(
            f"{row['name']}: chunks={row['chunk_count']}, "
            f"average_chars={row['average_chars']}, 95p_chars={row['95p_chars']}, "
            f"small_ratio={row['lessthan_200_ratio']}, "
            f"large_ratio={row['greaterthan_1200_ratio']}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_DIR / "tl1_rag_documents.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "chunk_experiment_report.json"),
    )
    args = parser.parse_args()

    run_experiment(
        input_jsonl=Path(args.input),
        output_report=Path(args.output),
    )


if __name__ == "__main__":
    main()
