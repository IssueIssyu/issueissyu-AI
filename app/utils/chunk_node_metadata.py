"""
청크 JSONL 행 -> 벡터 DB / MetadataFilters용 메타데이터.
메타데이터 만드는 공통 함수 파일이다.
여기만 고치면 두 경로가 같이 바뀐다. (JSONL 실험 스크립트(embed_chunks_gemini)와 LlamaIndex insert_nodes 경로)
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from llama_index.core.schema import TextNode

_OPTIONAL_FILTER_METADATA_KEYS = (
    "domain",
    "region",
    "source",
    "consulting_date",
    "consulting_category",
    "publish_date",
    "category",
    "subcategory",
    "predication",
    "department",
)

_STRUCTURE_KEYS = (
    "doc_id",
    "source_file",
    "source_path",
    "chunk_id",
    "chunk_index",
    "chunk_strategy",
    "chunk_size",
    "chunk_overlap",
)


def normalize_metadata_value(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def chunk_data_type(row: Mapping[str, Any]) -> str:
    value = row.get("data_type")
    if not value:
        raise ValueError("chunk row에 data_type이 없음")
    if value not in ("qna", "tl1"):
        raise ValueError(f"data_type은 'qna' 또는 'tl1'이어야 함 (받음: {value!r})")
    return str(value)


def build_chunk_metadata(row: Mapping[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for k in _STRUCTURE_KEYS:
        if k not in row:
            continue
        norm = normalize_metadata_value(row.get(k))
        if norm is not None:
            metadata[k] = norm

    data_type = chunk_data_type(row)
    metadata["data_type"] = data_type
    metadata["type"] = data_type

    for k in _OPTIONAL_FILTER_METADATA_KEYS:
        if k not in row:
            continue
        norm = normalize_metadata_value(row.get(k))
        if norm is not None:
            metadata[k] = norm

    return metadata


def text_node_from_chunk_row(
    row: Mapping[str, Any],
    *,
    text: str,
    node_id: str | None = None,
) -> TextNode:
    #insert_nodes에 넣을 TextNode. metadata는 항상 build_chunk_metadata(row)와 동일.
    nid = node_id if node_id is not None else str(row.get("chunk_id") or "")
    return TextNode(text=text, id_=nid, metadata=build_chunk_metadata(row))
