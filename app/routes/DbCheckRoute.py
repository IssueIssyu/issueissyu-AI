import time

from pydantic import BaseModel, Field

from fastapi import APIRouter
from sqlalchemy import select

from app.core.codes import SuccessCode
from app.core.deps import DbSessionDep
from app.core.responses import success_response
from app.models.DbConnectionCheck import DbConnectionCheck

router = APIRouter(prefix="/db-connection-check", tags=["db-check"])


def _default_test_id() -> int:
    return time.time_ns() // 1_000


class DbConnectionCheckCreate(BaseModel):
    id: int | None = None
    message: str | None = Field(default=None, max_length=8192)


@router.post("/")
async def create_db_connection_check(
    body: DbConnectionCheckCreate,
    session: DbSessionDep,
):
    row_id = body.id if body.id is not None else _default_test_id()
    row = DbConnectionCheck(id=row_id, message=body.message)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return success_response(
        result={"id": row.id, "message": row.message},
        success_code=SuccessCode.CREATED,
    )


@router.get("/")
async def list_db_connection_checks(session: DbSessionDep):
    result = await session.execute(select(DbConnectionCheck).order_by(DbConnectionCheck.id.desc()))
    rows = result.scalars().all()
    return success_response(
        result=[{"id": r.id, "message": r.message} for r in rows],
        success_code=SuccessCode.OK,
    )
