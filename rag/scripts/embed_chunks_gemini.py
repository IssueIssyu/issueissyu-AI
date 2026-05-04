from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from google import genai

from dotenv import load_dotenv

from chunk_module import load_jsonl, write_jsonl
from preprocess_module import OUTPUT_DIR


# 공식 문서: https://ai.google.dev/gemini-api/docs/embeddings?hl=ko#generate-embeddings
DEFAULT_MODEL = "gemini-embedding-2"
# app.utils.vector.DEFAULT_EMBEDDING_DIM 과 동일 (DB·쿼리 임베딩·검증과 불일치 시 검색 깨짐)
DEFAULT_OUTPUT_DIMENSIONALITY = 1536
# embed_content에 문자열 리스트를 넘기면 한 번의 요청으로 배치 임베딩 (RTT 감소)
DEFAULT_EMBED_BATCH_SIZE = 100

DEFAULT_EMBED_RETRY_ATTEMPTS = 8
DEFAULT_EMBED_RETRY_WAIT_MIN_S = 2
DEFAULT_EMBED_RETRY_WAIT_MAX_S = 120

# normalize_chunk: 줄 시작이 이 접두어 중 하나면 제외 (None이면 이 기본값 사용)
DEFAULT_NORMALIZE_SKIP_PREFIXES: tuple[str, ...] = (
    "[출처 기관]",
    "[상담 분류]",
    "[상담 일자]",
    "[상담 내용]",
)


def load_skip_line_prefixes(path: Path) -> tuple[str, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"normalize 설정은 JSON 객체여야 함: {path}")
    raw = data.get("skip_line_prefixes")
    if raw is None:
        raw = data.get("skip_prefixes")
    if raw is None:
        raise ValueError(
            f"normalize 설정에 skip_line_prefixes 또는 skip_prefixes 배열이 필요함: {path}"
        )
    if not isinstance(raw, list):
        raise ValueError(f"skip_line_prefixes는 문자열 배열이어야 함: {path}")
    return tuple(str(x) for x in raw)


def is_retryable_error(exc: BaseException) -> bool:
    from google.genai import errors as genai_errors

    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            ConnectionError,
            TimeoutError,
        ),
    )


EMBED_API_RETRY = Retrying(
    stop=stop_after_attempt(DEFAULT_EMBED_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=DEFAULT_EMBED_RETRY_WAIT_MIN_S,
        max=DEFAULT_EMBED_RETRY_WAIT_MAX_S,
    ),
    retry=retry_if_exception(is_retryable_error),
    reraise=True,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def gemini_model_id(model: str) -> str:
    #API,embedding_id용 모델 id (models/ 접두어 제거).
    m = model.strip()
    return m[len("models/") :] if m.startswith("models/") else m


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


def normalize_chunk(
    chunk_text: str,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
) -> str:
    raw = chunk_text.strip()
    if not raw:
        return ""

    lines = raw.splitlines()
    cleaned_lines = []
    prefixes = (
        DEFAULT_NORMALIZE_SKIP_PREFIXES
        if skip_line_prefixes is None
        else skip_line_prefixes
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if prefixes and stripped.startswith(prefixes):
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


def build_qna_embedding_text(
    row: Dict,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
) -> str:
    # TL1과 달리 QnA row의 text/rag_text에는 보통 제목 줄이 있어 split_title_body가 유효함.
    chunk_source = str(row.get("chunk_text") or "").strip()
    full_title, _ = split_title_body(
        str(row.get("rag_text") or row.get("text") or "").strip()
    )
    body = normalize_chunk(chunk_source, skip_line_prefixes=skip_line_prefixes)
    if full_title and full_title != "제목 없음":
        return f"[제목] {full_title}\n[본문] {body}"
    return body


def build_tl1_embedding_text(
    row: Dict,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
) -> str:
    # TL1: text/rag_text에 "제목 :" 형식이 없어 QnA처럼 제목 슬롯을 두면 [제목] 제목 없음만 붙음, 본문만 임베딩.
    chunk_source = str(
        row.get("chunk_text") or row.get("rag_text") or row.get("text") or ""
    ).strip()
    return normalize_chunk(chunk_source, skip_line_prefixes=skip_line_prefixes)


def build_embedding_text(
    row: Dict,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
) -> str:
    row_type = chunk_data_type(row)
    if row_type == "qna":
        return build_qna_embedding_text(row, skip_line_prefixes=skip_line_prefixes)
    return build_tl1_embedding_text(row, skip_line_prefixes=skip_line_prefixes)


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


def _mock_embedding_vector(text: str, output_dimensionality: Optional[int]) -> List[float]:
    dim = output_dimensionality or DEFAULT_OUTPUT_DIMENSIONALITY
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dim):
        byte_val = digest[i % len(digest)]
        values.append((byte_val / 255.0) * 2 - 1)
    return values


def embed_texts(
    texts: List[str],
    model: str,
    output_dimensionality: Optional[int] = None,
    task_type: Optional[str] = None,
    mock: bool = False,
    client: Optional[genai.Client] = None,
) -> List[List[float]]:
    if not texts:
        return []

    if mock:
        return [_mock_embedding_vector(t, output_dimensionality) for t in texts]

    if client is None:
        raise RuntimeError("Gemini client 필요")

    from google.genai import types

    model_id = gemini_model_id(model)
    config_fields: Dict[str, object] = {}
    if output_dimensionality is not None:
        config_fields["output_dimensionality"] = output_dimensionality
    # gemini-embedding-2는 task_type 미지원 — 필요하면 텍스트 앞에 설명 붙이는 방식
    if task_type is not None and "embedding-001" in model_id:
        config_fields["task_type"] = task_type
    config = types.EmbedContentConfig(**config_fields) if config_fields else None

    kwargs: Dict[str, object] = {"model": model_id, "contents": texts}
    if config is not None:
        kwargs["config"] = config

    result = EMBED_API_RETRY(lambda: client.models.embed_content(**kwargs))
    if not result.embeddings:
        raise RuntimeError("embed_content 임베딩 없음")
    if len(result.embeddings) != len(texts):
        raise RuntimeError(
            f"embed_content 배치 크기 불일치: 요청 {len(texts)}개, 응답 {len(result.embeddings)}개"
        )
    return [list(emb.values) for emb in result.embeddings]


def embed_text(
    text: str,
    model: str,
    output_dimensionality: Optional[int] = None,
    task_type: Optional[str] = None,
    mock: bool = False,
    client: Optional[genai.Client] = None,
) -> List[float]:
    return embed_texts(
        [text],
        model=model,
        output_dimensionality=output_dimensionality,
        task_type=task_type,
        mock=mock,
        client=client,
    )[0]


def build_embedding_rows(
    chunk_rows: Iterable[Dict],
    model: str,
    output_dimensionality: Optional[int],
    mock: bool = False,
    limit: Optional[int] = None,
    log_every: int = 10,
    task_type: Optional[str] = None,
    client: Optional[genai.Client] = None,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
) -> List[Dict]:
    work: List[Dict] = []

    for idx, row in enumerate(chunk_rows):
        if limit is not None and len(work) >= limit:
            break

        row_type = chunk_data_type(row)
        if row_type == "tl1":
            raw_for_normalize = str(
                row.get("chunk_text") or row.get("rag_text") or row.get("text") or ""
            ).strip()
        else:
            raw_for_normalize = str(row.get("chunk_text") or "").strip()
        body = normalize_chunk(raw_for_normalize, skip_line_prefixes=skip_line_prefixes)
        if not body:
            continue

        document_text = build_embedding_text(row, skip_line_prefixes=skip_line_prefixes)
        chunk_id = str(row.get("chunk_id") or f"row::{idx}")
        work.append(
            {
                "row": row,
                "document_text": document_text,
                "chunk_id": chunk_id,
            }
        )

    out_rows: List[Dict] = []
    batch_size = max(1, batch_size)
    if gemini_model_id(model) == "gemini-embedding-2" and not mock:
        if batch_size != 1:
            print(
                "gemini-embedding-2는 embed_content 다중 텍스트 시 "
                f"응답 임베딩이 1건만 와 batch_size를 {batch_size} → 1로 조정합니다.",
                flush=True,
            )
        batch_size = 1

    model_for_id = gemini_model_id(model)

    for start in range(0, len(work), batch_size):
        batch = work[start : start + batch_size]
        texts = [item["document_text"] for item in batch]
        vectors = embed_texts(
            texts=texts,
            model=model,
            output_dimensionality=output_dimensionality,
            task_type=task_type,
            mock=mock,
            client=client,
        )

        for item, vector in zip(batch, vectors):
            row = item["row"]
            document_text = item["document_text"]
            chunk_id = item["chunk_id"]
            out_rows.append(
                {
                    "embedding_id": f"{model_for_id}::{chunk_id}::{sha1(document_text)[:10]}",
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
        default=DEFAULT_OUTPUT_DIMENSIONALITY,
        choices=[768, 1536, 3072],
        help="Embedding dimension (default: 1536; Gemini embedding-2: 768, 1536, 3072)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="임베딩할 최대 청크 수 (미지정 시 전체). 테스트 시에만 지정 권장",
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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_EMBED_BATCH_SIZE,
        help="embed_content 한 요청당 텍스트 개수. gemini-embedding-2는 API 제한으로 실호출 시 1로 강제",
    )
    parser.add_argument(
        "--normalize-config",
        type=Path,
        default=None,
        metavar="PATH",
        help="JSON 파일: skip_line_prefixes(또는 skip_prefixes) 문자열 배열",
    )
    parser.add_argument(
        "--skip-line-prefix",
        action="append",
        default=None,
        metavar="PREFIX",
        help="normalize_chunk에서 제거할 줄 접두어. 지정 시 기본 접두어 대신 이 목록만 사용",
    )
    args = parser.parse_args()
    if args.log_every < 0:
        parser.error("--log-every 음수면 안됨")
    if args.batch_size < 1:
        parser.error("--batch-size는 1 이상이어야 함")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit은 1 이상이어야 함")
    if args.normalize_config is not None and args.skip_line_prefix is not None:
        parser.error("--normalize-config와 --skip-line-prefix는 함께 쓸 수 없음")
    skip_line_prefixes: Optional[tuple[str, ...]] = None
    if args.normalize_config is not None:
        if not args.normalize_config.is_file():
            parser.error(f"normalize 설정 파일 없음: {args.normalize_config}")
        skip_line_prefixes = load_skip_line_prefixes(args.normalize_config)
    elif args.skip_line_prefix is not None:
        skip_line_prefixes = tuple(args.skip_line_prefix)

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
        batch_size=args.batch_size,
        skip_line_prefixes=skip_line_prefixes,
    )
    write_jsonl(output_path, out_rows)
    print(f"[done] embedded={len(out_rows)} output={output_path}")


if __name__ == "__main__":
    main()
