import json
from pathlib import Path


RAW_ROOT = Path("../raw/tl1")
OUTPUT_DIR = Path("../output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_JSONL = OUTPUT_DIR / "tl1_rag_documents.jsonl"
OUTPUT_PREVIEW = OUTPUT_DIR / "tl1_rag_preview.json"
OUTPUT_REPORT = OUTPUT_DIR / "tl1_preprocessing_report.json"


def safe_get(data, *keys, default=""):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def clean_text(text: str) -> str:
    if not text:
        return ""

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    return "\n".join(lines).strip()


def build_rag_text(category: str, subcategory: str, predication: str, department: str, text: str) -> str:
    parts = []

    if category:
        parts.append(f"[민원 대분류] {category}")
    if subcategory:
        parts.append(f"[민원 소분류] {subcategory}")
    if predication:
        parts.append(f"[민원 유형] {predication}")
    if department:
        parts.append(f"[담당 부서] {department}")

    parts.append(f"[민원 내용]\n{text}")

    return "\n".join(parts)


def iter_json_files(root: Path):
    for path in root.rglob("*.json"):
        yield path


def main():
    total_files = 0
    total_documents = 0
    valid_documents = 0
    category_counter = {}
    preview_rows = []

    with OUTPUT_JSONL.open("w", encoding="utf-8") as jsonl_file:
        for json_path in iter_json_files(RAW_ROOT):
            total_files += 1

            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            documents = data.get("documents", [])
            total_documents += len(documents)

            for doc in documents:
                text = clean_text(doc.get("Q_refined", ""))
                if not text:
                    continue

                doc_id = doc.get("id", "")
                publish_date = doc.get("publish_date", "")
                category = safe_get(doc, "labeling", "intent", "category", default="")
                subcategory = safe_get(doc, "labeling", "intent", "subcategory", default="")
                predication = safe_get(doc, "labeling", "intent", "predication", default="")
                department = safe_get(doc, "labeling", "department", default="")

                rag_text = build_rag_text(
                    category=category,
                    subcategory=subcategory,
                    predication=predication,
                    department=department,
                    text=text,
                )

                row = {
                    "doc_id": doc_id,
                    "source_file": json_path.name,
                    "source_path": str(json_path),
                    "publish_date": publish_date,
                    "category": category,
                    "subcategory": subcategory,
                    "predication": predication,
                    "department": department,
                    "text": text,
                    "rag_text": rag_text,
                }

                jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                valid_documents += 1

                if len(preview_rows) < 5:
                    preview_rows.append(row)

                if category:
                    category_counter[category] = category_counter.get(category, 0) + 1

    with OUTPUT_PREVIEW.open("w", encoding="utf-8") as f:
        json.dump(preview_rows, f, ensure_ascii=False, indent=2)

    report = {
        "total_files": total_files,
        "total_documents": total_documents,
        "valid_documents": valid_documents,
        "category_counts": dict(sorted(category_counter.items(), key=lambda x: x[0])),
    }

    with OUTPUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("전처리 완료")
    print(f"처리한 파일 수: {total_files}")
    print(f"전체 documents 수: {total_documents}")
    print(f"전처리 결과 수: {valid_documents}")
    print(f"저장 파일: {OUTPUT_JSONL}")
    print(f"미리보기 파일: {OUTPUT_PREVIEW}")
    print(f"리포트 파일: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()