from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from google.genai.errors import ClientError as GenaiClientError, ServerError as GenaiServerError
from llama_index.core.schema import TextNode
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

# python -m rag.scripts.insert_chunks_to_vector 형태 실행 기준
from app.core.config import settings
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import DomainVectorConfig, VectorDomain
from app.utils.chunk_node_metadata import build_chunk_metadata
from app.utils.chunk_text_normalize import load_skip_line_prefixes, normalize_chunk
from rag.scripts.chunk_module import iter_jsonl

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_PENDING_BATCHES_FACTOR = 4


# ── checkpoint helpers ──────────────────────────────────────────────

def _checkpoint_path(input_path: Path) -> Path:
    h = hashlib.md5(str(input_path.resolve()).encode()).hexdigest()[:8]
    return input_path.parent / f".ckpt_{input_path.stem}_{h}.json"


def _load_checkpoint(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_checkpoint(path: Path, offset: int, inserted: int, skipped: int) -> None:
    with path.open("w") as f:
        json.dump({"offset": offset, "inserted": inserted, "skipped": skipped}, f)


def _remove_checkpoint(path: Path) -> None:
    path.unlink(missing_ok=True)


def build_service(*, embed_workers: int = 10) -> VectorStoreService:
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
        embedding_batch_size_override=settings.gemini_embedding_batch_size,
        embed_workers=embed_workers,
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


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, TimeoutError)):
        return True
    if isinstance(exc, GenaiServerError):
        return True
    if isinstance(exc, GenaiClientError) and getattr(exc, "code", None) == 429:
        return True
    return False


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    stop=stop_after_attempt(8),
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
        "--concurrency",
        type=int,
        default=1,
        help="동시 insert 배치 수(각각 별도 VectorStoreService). 2~6 권장. API 한도/DB 부하에 맞춰 조절.",
    )
    parser.add_argument(
        "--max-pending-batches",
        type=int,
        default=None,
        metavar="N",
        help="큐에 쌓아 둘 배치 상한(기본: concurrency * 4). 메모리·백프레셔 조절.",
    )
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
    parser.add_argument(
        "--embed-workers",
        type=int,
        default=10,
        help="배치 내 임베딩 병렬 스레드 수(기본 10). API 429 발생 시 줄일 것.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="이전 체크포인트를 무시하고 처음부터 실행",
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
    if args.concurrency < 1:
        raise ValueError("--concurrency는 1 이상이어야 함")
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

    # ── checkpoint resume ──
    ckpt_path = _checkpoint_path(args.input)
    total = 0
    skipped = 0
    processed = 0

    if not args.no_resume and args.start_offset == 0:
        ckpt = _load_checkpoint(ckpt_path)
        if ckpt:
            args.start_offset = ckpt["offset"]
            total = ckpt.get("inserted", 0)
            skipped = ckpt.get("skipped", 0)
            print(
                f"[resume] 체크포인트 발견 → offset={args.start_offset} "
                f"inserted={total} skipped={skipped}"
            )
    elif args.no_resume:
        _remove_checkpoint(ckpt_path)

    table_name = ""
    seen_ids: set[str] | None = None if args.no_dedupe_node else set()

    max_pending = args.max_pending_batches
    if max_pending is None:
        max_pending = max(
            args.concurrency * DEFAULT_MAX_PENDING_BATCHES_FACTOR,
            args.concurrency + 1,
        )

    if args.concurrency <= 1:
        svc = build_service(embed_workers=args.embed_workers)
        nodes: list[TextNode] = []

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
                _save_checkpoint(ckpt_path, offset=idx + 1, inserted=total, skipped=skipped)
                print(f"[progress] inserted={total} skipped={skipped} last_batch={len(nodes)}")
                nodes = []

        if nodes:
            table_name = await insert_batch_with_retry(svc, nodes, domain)
            total += len(nodes)

        _remove_checkpoint(ckpt_path)
        print(f"[done] table={table_name} inserted_total={total} skipped={skipped} processed={processed}")
        return

    # 병렬: 서비스 풀(클라이언트 분리) + 제한된 in-flight Task
    svc_pool: asyncio.Queue[VectorStoreService] = asyncio.Queue()
    for _ in range(args.concurrency):
        await svc_pool.put(build_service(embed_workers=args.embed_workers))

    async def insert_with_pool(batch: list[TextNode]) -> tuple[str, int]:
        svc = await svc_pool.get()
        try:
            tname = await insert_batch_with_retry(svc, batch, domain)
            return tname, len(batch)
        finally:
            await svc_pool.put(svc)

    tasks: list[asyncio.Task[tuple[str, int]]] = []
    task_start_idx: dict[asyncio.Task, int] = {}
    nodes_buf: list[TextNode] = []
    batch_first_row: int | None = None
    last_read_idx: int = args.start_offset

    async def drain_some_tasks() -> None:
        nonlocal tasks, table_name, total
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            tname, n = d.result()
            total += n
            if tname:
                table_name = tname
            task_start_idx.pop(d, None)
            print(f"[progress] inserted={total} skipped={skipped} last_batch={n}")
        tasks = list(pending)
        # safe checkpoint = earliest pending batch start, or next row
        if task_start_idx:
            safe = min(task_start_idx.values())
        else:
            safe = last_read_idx + 1
        _save_checkpoint(ckpt_path, offset=safe, inserted=total, skipped=skipped)

    for idx, row in enumerate(iter_jsonl(args.input)):
        if idx < args.start_offset:
            continue
        if args.limit is not None and processed >= args.limit:
            break
        last_read_idx = idx
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
            if batch_first_row is None:
                batch_first_row = idx
            nodes_buf.append(node)

        except Exception as e:
            print(
                f"[skip] exception idx={idx} "
                f"chunk_id={row.get('chunk_id')} "
                f"error={type(e).__name__}: {e}"
            )
            skipped += 1
            continue

        if len(nodes_buf) >= args.batch_size:
            batch = nodes_buf
            nodes_buf = []
            while len(tasks) >= max_pending:
                await drain_some_tasks()
            t = asyncio.create_task(insert_with_pool(batch))
            task_start_idx[t] = batch_first_row or idx
            tasks.append(t)
            batch_first_row = None

    if nodes_buf:
        while len(tasks) >= max_pending:
            await drain_some_tasks()
        t = asyncio.create_task(insert_with_pool(nodes_buf))
        task_start_idx[t] = batch_first_row or last_read_idx
        tasks.append(t)

    if tasks:
        results = await asyncio.gather(*tasks)
        for tname, n in results:
            total += n
            if tname:
                table_name = tname
            print(f"[progress] inserted={total} skipped={skipped} last_batch={n}")

    if not table_name:
        table_name = build_service().get_table_name(domain=domain.value)

    _remove_checkpoint(ckpt_path)
    print(
        f"[done] table={table_name} inserted_total={total} skipped={skipped} "
        f"processed={processed} concurrency={args.concurrency}"
    )


if __name__ == "__main__":
    asyncio.run(main())
