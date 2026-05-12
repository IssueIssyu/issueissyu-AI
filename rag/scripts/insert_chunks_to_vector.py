from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx
from llama_index.core.schema import TextNode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# python -m rag.scripts.insert_chunks_to_vector 형태 실행 기준
from app.core.config import settings
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import DomainVectorConfig, VectorDomain
from app.utils.chunk_node_metadata import build_chunk_metadata
from rag.scripts.chunk_module import load_jsonl

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

def row_to_node(row: dict) -> TextNode:
    text = (row.get("chunk_text") or row.get("text") or "").strip()
    if not text:
        raise ValueError("empty text")
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
    return parser.parse_args()


async def main():
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(f"input 파일 없음: {args.input}")
    if args.batch_size < 1:
        raise ValueError("--batch-size는 1 이상이어야 함")
    if args.start_offset < 0:
        raise ValueError("--start-offset은 0 이상이어야 함")

    try:
        domain = VectorDomain(args.domain.lower())
    except ValueError as exc:
        raise ValueError(f"--domain은 {', '.join(d.value for d in VectorDomain)} 중 하나여야 함") from exc

    svc = build_service()
    rows = load_jsonl(args.input)
    nodes: list[TextNode] = []
    total = 0
    skipped = 0
    processed = 0
    table_name = ""
    seen_ids: set[str] = set()

    for idx, row in enumerate(rows):
        if idx < args.start_offset:
            continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        try:
            node = row_to_node(row)
            node_id = node.node_id
            if not node_id or node_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(node_id)
            nodes.append(node)
        except Exception:
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