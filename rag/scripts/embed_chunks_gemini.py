from __future__ import annotations

import argparse
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from google import genai

from dotenv import load_dotenv

from chunk_module import load_jsonl, write_jsonl
from preprocess_module import OUTPUT_DIR


# 공식 문서: https://ai.google.dev/gemini-api/docs/embeddings?hl=ko#generate-embeddings
DEFAULT_MODEL = "gemini-embedding-2"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def split_title_body(text: str) -> tuple[str, str]:
    raw = text.strip()
    if not raw:
        return "제목 없음", ""

    lines = raw.splitlines()
    first_line = lines[0].strip()

    if first_line.startswith("제목 :"):
        title = first_line[len("제목 :") :].strip() or "제목 없음"
        body = "\n".join(lines[1:]).strip()
        return title, body

    return "제목 없음", raw


def normalize_chunk(chunk_text: str) -> str:
    raw = chunk_text.strip()
    if not raw:
        return ""

    lines = raw.splitlines()
    cleaned_lines = []
    skip_prefixes = ("[출처 기관]", "[상담 분류]", "[상담 일자]", "[상담 내용]")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(skip_prefixes):
            continue
        if stripped.startswith("제목 :"):
            continue
        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines).strip()


def chunk_data_type(row: Dict) -> str:
    # 청크 row의 data_type만 사용
    value = row.get("data_type")
    if not value:
        raise ValueError(
            "chunk row에 data_type이 없음"
        )
    if value not in ("qna", "tl1"):
        raise ValueError(f"data_type은 'qna' 또는 'tl1'이어야 함 (받음: {value!r})")
    return value


def build_qna_embedding_text(row: Dict) -> str:
    # 제목은 원본 문서 필드에서만, 청크 분할 뒤 chunk_text에는 "제목 :" 줄이 없는 경우가 많아서, chunk에서 제목을 먼저 찾는 방식은 대부분 text로 폴백
    chunk_source = str(row.get("chunk_text") or "").strip()
    full_title, _ = split_title_body(
        str(row.get("text") or row.get("rag_text") or "").strip()
    )
    body = normalize_chunk(chunk_source)
    return f"[제목] {full_title}\n[본문] {body}"


def build_tl1_embedding_text(row: Dict) -> str:
    chunk_source = str(row.get("chunk_text") or "").strip()
    body = normalize_chunk(chunk_source)
    return f"[민원] {body}"


def build_embedding_text(row: Dict) -> str:
    row_type = chunk_data_type(row)
    if row_type == "qna":
        return build_qna_embedding_text(row)
    return build_tl1_embedding_text(row)


def build_chunk_metadata(row: Dict) -> Dict:
    keep_keys = [
        "doc_id",
        "source_file",
        "source_path",
        "chunk_id",
        "chunk_index",
        "chunk_strategy",
        "chunk_size",
        "chunk_overlap",
    ]
    metadata = {k: row.get(k) for k in keep_keys if k in row}
    metadata["type"] = chunk_data_type(row)
    return metadata


def embed_text(
    text: str,
    model: str,
    output_dimensionality: Optional[int] = None,
    task_type: Optional[str] = None,
    mock: bool = False,
    client: Optional[genai.Client] = None,
) -> List[float]:
    if mock:
        dim = output_dimensionality or 768
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for i in range(dim):
            byte_val = digest[i % len(digest)]
            values.append((byte_val / 255.0) * 2 - 1)
        return values

    if client is None:
        raise RuntimeError("Gemini client 필요")

    from google.genai import types

    m = model.strip()
    model_id = m[len("models/") :] if m.startswith("models/") else m
    config_fields: Dict[str, object] = {}
    if output_dimensionality is not None:
        config_fields["output_dimensionality"] = output_dimensionality
    # gemini-embedding-2는 task_type 미지원 — 필요하면 텍스트 앞에 설명 붙이는 방식
    if task_type is not None and "embedding-001" in model_id:
        config_fields["task_type"] = task_type
    config = types.EmbedContentConfig(**config_fields) if config_fields else None

    kwargs: Dict[str, object] = {"model": model_id, "contents": text}
    if config is not None:
        kwargs["config"] = config

    result = client.models.embed_content(**kwargs)
    if not result.embeddings:
        raise RuntimeError("embed_content 임베딩 없음")
    return list(result.embeddings[0].values)


def build_embedding_rows(
    chunk_rows: Iterable[Dict],
    model: str,
    output_dimensionality: Optional[int],
    mock: bool = False,
    limit: Optional[int] = None,
    log_every: int = 10,
    task_type: Optional[str] = None,
    client: Optional[genai.Client] = None,
) -> List[Dict]:
    out_rows = []

    for idx, row in enumerate(chunk_rows):
        if limit is not None and len(out_rows) >= limit:
            break

        chunk_source = str(row.get("chunk_text") or "").strip()
        body = normalize_chunk(chunk_source)
        if not body:
            continue

        document_text = build_embedding_text(row)
        vector = embed_text(
            text=document_text,
            model=model,
            output_dimensionality=output_dimensionality,
            task_type=task_type,
            mock=mock,
            client=client,
        )

        chunk_id = str(row.get("chunk_id") or f"row::{idx}")
        out_rows.append(
            {
                "embedding_id": f"{chunk_id}::{sha1(document_text)[:10]}",
                "chunk_id": chunk_id,
                "model": model,
                "created_at": now_utc(),
                "embedding_dim": len(vector),
                "text_hash": sha1(document_text),
                "text_for_embedding": document_text,
                "vector": vector,
                "metadata": build_chunk_metadata(row),
            }
        )

        if log_every > 0 and len(out_rows) % log_every == 0:
            print(f"[progress] embedded={len(out_rows)}")

    return out_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_DIR / "qna_chunks_paragraph.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "qna_embeddings_sample_gemini2.jsonl"),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--task-type",
        default=None,
        metavar="TYPE",
        help="gemini-embedding-001 전용 task_type. embedding-2에는 적용되지 않음",
    )
    parser.add_argument(
        "--output-dimensionality",
        type=int,
        default=768,
        help="Embedding dimension (recommended: 768, 1536, 3072)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="빠른 샘플 테스트용 제한값",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="실제 API 대신 테스트용 가짜 벡터",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10,
    )
    args = parser.parse_args()
    if args.log_every < 0:
        parser.error("--log-every 음수면 안됨")

    client = None
    if not args.mock:
        from google import genai

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 없음")
        client = genai.Client(api_key=api_key)

    input_path = Path(args.input)
    output_path = Path(args.output)

    chunk_rows = load_jsonl(input_path)
    print(f"[start] input_rows={len(chunk_rows)} model={args.model}")

    out_rows = build_embedding_rows(
        chunk_rows=chunk_rows,
        model=args.model,
        output_dimensionality=args.output_dimensionality,
        mock=args.mock,
        limit=args.limit,
        log_every=args.log_every,
        task_type=args.task_type,
        client=client,
    )
    write_jsonl(output_path, out_rows)
    print(f"[done] embedded={len(out_rows)} output={output_path}")


if __name__ == "__main__":
    main()
