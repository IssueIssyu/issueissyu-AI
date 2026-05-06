from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Query
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import FilterOperator, MetadataFilter, MetadataFilters

from app.core.codes import SuccessCode
from app.core.deps import VectorStoreServiceDep
from app.core.responses import success_response
from app.services.vector_domains import VectorDomain

router = APIRouter(prefix="/vector-test", tags=["vector-test"])


@router.post("/insert")
async def insert_test_node(vector_store_service: VectorStoreServiceDep):
    chunk_id = f"vector-test-{uuid4().hex[:12]}"
    node = TextNode(
        text="도로 옆에 생활 쓰레기가 쌓여 있어 악취가 발생하고 있습니다.",
        id_=chunk_id,
        metadata={
            "data_type": "qna",
            "category": "환경",
            "department": "청소행정과",
            "chunk_id": chunk_id,
            "source": "manual-test",
        },
    )

    table_name = await vector_store_service.ainsert_nodes(
        [node],
        domain=VectorDomain.COMPLAINT,
    )

    return success_response(
        result={
            "status": "inserted",
            "table_name": table_name,
            "chunk_id": chunk_id,
        },
        success_code=SuccessCode.CREATED,
    )


@router.get("/retrieve")
async def retrieve_test_node(
    vector_store_service: VectorStoreServiceDep,
    query: str = Query(default="쓰레기 악취 민원"),
    top_k: int = Query(default=3, ge=1, le=20),
):
    results = await vector_store_service.aretrieve(
        query,
        domain=VectorDomain.COMPLAINT,
        similarity_top_k=top_k,
    )

    return success_response(
        result={
            "count": len(results),
            "results": [
                {
                    "text": result.node.get_content(),
                    "score": result.score,
                    "metadata": result.node.metadata,
                }
                for result in results
            ],
        },
        success_code=SuccessCode.OK,
    )


@router.get("/retrieve-filtered")
async def retrieve_filtered_test_node(
    vector_store_service: VectorStoreServiceDep,
    query: str = Query(default="쓰레기 악취 민원"),
    data_type: str = Query(default="qna"),
    category: str = Query(default="환경"),
    top_k: int = Query(default=3, ge=1, le=20),
):
    filters = MetadataFilters(
        filters=[
            MetadataFilter(key="data_type", value=data_type, operator=FilterOperator.EQ),
            MetadataFilter(key="category", value=category, operator=FilterOperator.EQ),
        ]
    )
    results = await vector_store_service.aretrieve(
        query,
        domain=VectorDomain.COMPLAINT,
        similarity_top_k=top_k,
        filters=filters,
    )

    return success_response(
        result={
            "count": len(results),
            "applied_filters": {"data_type": data_type, "category": category},
            "results": [
                {
                    "text": result.node.get_content(),
                    "score": result.score,
                    "metadata": result.node.metadata,
                }
                for result in results
            ],
        },
        success_code=SuccessCode.OK,
    )
