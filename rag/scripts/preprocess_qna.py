import json
from pathlib import Path


RAW_ROOT = Path("../raw/qna")
OUTPUT_DIR = Path("../output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_JSONL = OUTPUT_DIR / "qna_rag_documents.jsonl"
OUTPUT_PREVIEW = OUTPUT_DIR / "qna_rag_preview.json"
OUTPUT_REPORT = OUTPUT_DIR / "qna_preprocessing_report.json"


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("_x000D_", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    return "\n".join(lines).strip()


def build_rag_text(source: str, consulting_category: str, consulting_date: str, consulting_content: str) -> str:
    parts = []

    if source:
        parts.append(f"[출처 기관] {source}")
    if consulting_category and consulting_category != "-":
        parts.append(f"[상담 분류] {consulting_category}")
    if consulting_date:
        parts.append(f"[상담 일자] {consulting_date}")

    parts.append(f"[상담 내용]\n{consulting_content}")

    return "\n".join(parts)


def iter_json_files(root: Path):
    for path in root.rglob("*.json"):
        yield path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_records(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def main():
    total_files = 0
    total_records = 0
    valid_records = 0
    source_counter = {}
    category_counter = {}
    preview_rows = []

    with OUTPUT_JSONL.open("w", encoding="utf-8") as jsonl_file:
        for json_path in iter_json_files(RAW_ROOT):
            total_files += 1

            data = load_json(json_path)
            records = normalize_records(data)
            total_records += len(records)

            for record in records:
                source = record.get("source", "")
                source_id = str(record.get("source_id", ""))
                consulting_date = str(record.get("consulting_date", ""))
                consulting_category = record.get("consulting_category", "")
                consulting_content = clean_text(record.get("consulting_content", ""))

                if not consulting_content:
                    continue

                rag_text = build_rag_text(
                    source=source,
                    consulting_category=consulting_category,
                    consulting_date=consulting_date,
                    consulting_content=consulting_content,
                )

                row = {
                    "doc_id": source_id,
                    "source_file": json_path.name,
                    "source_path": str(json_path),
                    "source": source,
                    "consulting_date": consulting_date,
                    "consulting_category": consulting_category,
                    "text": consulting_content,
                    "rag_text": rag_text,
                }

                jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                valid_records += 1

                if len(preview_rows) < 5:
                    preview_rows.append(row)

                if source:
                    source_counter[source] = source_counter.get(source, 0) + 1

                if consulting_category and consulting_category != "-":
                    category_counter[consulting_category] = category_counter.get(consulting_category, 0) + 1

    report = {
        "total_files": total_files,
        "total_records": total_records,
        "valid_records": valid_records,
        "source_counts": dict(sorted(source_counter.items(), key=lambda x: x[0])),
        "consulting_category_counts": dict(sorted(category_counter.items(), key=lambda x: x[0])),
    }

    with OUTPUT_PREVIEW.open("w", encoding="utf-8") as f:
        json.dump(preview_rows, f, ensure_ascii=False, indent=2)

    with OUTPUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("QnA 전처리 완료")
    print(f"처리한 파일 수: {total_files}")
    print(f"전체 레코드 수: {total_records}")
    print(f"전처리 결과 수: {valid_records}")
    print(f"저장 파일: {OUTPUT_JSONL}")
    print(f"미리보기 파일: {OUTPUT_PREVIEW}")
    print(f"리포트 파일: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()