from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx
from llama_index.core.schema import TextNode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import DomainVectorConfig, VectorDomain
from app.utils.chunk_node_metadata import build_chunk_metadata
from app.utils.chunk_text_normalize import load_skip_line_prefixes, normalize_chunk
from rag.scripts.chunk_module import iter_jsonl

DEFAULT_BATCH_SIZE = 50


def build_service() -> VectorStoreService:
    api_key_secret = settings.gemini_api_key
    if api_key_secret is None:
        raise RuntimeError(
            "GEMINI_API_KEY가 없습니다. .env 또는 환경 변수 GEMINI_API_KEY를 설정한 뒤 다시 실행하세요."
        )
    domain_configs = {
        VectorDomain.COMPLAINT: DomainVectorConfig(
            table_name="complaint",
            embedding_model=settings.gemini_embedding_model,
            embed_dim=settings.vector_embed_dim,
        ),
        # 필요 도메인 추가
    }
    return VectorStoreService(
        database_url=settings.sync_database_url,
        async_database_url=settings.async_database_url,
        api_key=api_key_secret.get_secret_value(),
        table_name=settings.vector_table_name,
        default_embedding_model=settings.gemini_embedding_model,
        default_embed_dim=settings.vector_embed_dim,
        domain_configs=domain_configs,
        hybrid_search=settings.vector_hybrid_search,
        text_search_config=settings.vector_text_search_config,
    )


def row_to_node(
    row: dict,
    *,
    skip_line_prefixes: tuple[str, ...] | None = None,
    footer_line_prefixes: tuple[str, ...] | None = None,
    raw_text: bool = False,
) -> TextNode:
    raw = (row.get("chunk_text") or row.get("text") or "").strip()
    if not raw:
        raise ValueError("empty text")
    if raw_text:
        text = raw
    else:
        text = normalize_chunk(
            raw,
            skip_line_prefixes=skip_line_prefixes,
            footer_line_prefixes=footer_line_prefixes,
        )
    if not text:
        raise ValueError("empty text after normalize")
    chunk_id = str(row.get("chunk_id") or "")
    return TextNode(
        text=text,
        id_=chunk_id,
        metadata=build_chunk_metadata(row),
    )


@retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, TimeoutError)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def insert_batch_with_retry(
    svc: VectorStoreService,
    nodes: list[TextNode],
    domain: VectorDomain,
) -> str:
    return await svc.ainsert_nodes(nodes, domain=domain)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--domain", type=str, default=VectorDomain.COMPLAINT.value)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument(
        "--normalize-config",
        type=Path,
        default=None,
        metavar="PATH",
        help="JSON: skip_line_prefixes(또는 skip_prefixes) 배열",
    )
    parser.add_argument(
        "--skip-line-prefix",
        action="append",
        default=None,
        metavar="PREFIX",
        help="직접 제거할 prefix를 추가",
    )
    parser.add_argument(
        "--no-chunk-normalize",
        action="store_true",
        help="정규화 생략(원문 그대로 저장)",
    )
    parser.add_argument(
        "--no-footer-strip",
        action="store_true",
        help="푸터 제거만 끄기",
    )
    parser.add_argument(
        "--no-dedupe-node",
        action="store_true",
        help="입력이 이미 유일하거나 DB/상위 파이프라인에서 중복을 처리할 때 사용",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(f"input 파일 없음: {args.input}")
    if args.batch_size < 1:
        raise ValueError("--batch-size는 1 이상이어야 함")
    if args.start_offset < 0:
        raise ValueError("--start-offset은 0 이상이어야 함")
    if args.normalize_config is not None and args.skip_line_prefix is not None:
        raise ValueError("--normalize-config와 --skip-line-prefix는 함께 쓸 수 없음")

    try:
        domain = VectorDomain(args.domain.lower())
    except ValueError as exc:
        raise ValueError(f"--domain은 {', '.join(d.value for d in VectorDomain)} 중 하나여야 함") from exc

    skip_line_prefixes: tuple[str, ...] | None = None
    if args.normalize_config is not None:
        if not args.normalize_config.is_file():
            raise FileNotFoundError(f"normalize 설정 파일 없음: {args.normalize_config}")
        skip_line_prefixes = load_skip_line_prefixes(args.normalize_config)
    elif args.skip_line_prefix is not None:
        skip_line_prefixes = tuple(args.skip_line_prefix)

    footer_line_prefixes: tuple[str, ...] | None = () if args.no_footer_strip else None

    svc = build_service()
    nodes: list[TextNode] = []
    total = 0
    skipped = 0
    processed = 0
    table_name = ""
    seen_ids: set[str] | None = None if args.no_dedupe_node else set()

    for idx, row in enumerate(iter_jsonl(args.input)):
        if idx < args.start_offset:
            continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        try:
            node = row_to_node(
                row,
                skip_line_prefixes=skip_line_prefixes,
                footer_line_prefixes=footer_line_prefixes,
                raw_text=args.no_chunk_normalize,
            )
            node_id = node.node_id
            if not node_id:
                print(f"[skip] missing node_id idx={idx} chunk_id={row.get('chunk_id')}")
                skipped += 1
                continue

            if seen_ids is not None:
                if node_id in seen_ids:
                    print(f"[skip] duplicated node_id idx={idx} node_id={node_id}")
                    skipped += 1
                    continue
                seen_ids.add(node_id)
            nodes.append(node)

        except Exception as e:
            print(
                f"[skip] exception idx={idx} "
                f"chunk_id={row.get('chunk_id')} "
                f"error={type(e).__name__}: {e}"
            )
            skipped += 1
            continue
        if len(nodes) >= args.batch_size:
            table_name = await insert_batch_with_retry(svc, nodes, domain)
            total += len(nodes)
            print(f"[progress] inserted={total} skipped={skipped} last_batch={len(nodes)}")
            nodes = []

    if nodes:
        table_name = await insert_batch_with_retry(svc, nodes, domain)
        total += len(nodes)

    print(f"[done] table={table_name} inserted_total={total} skipped={skipped} processed={processed}")


if __name__ == "__main__":
    asyncio.run(main())
