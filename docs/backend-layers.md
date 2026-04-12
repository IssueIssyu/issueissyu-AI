# 백엔드 레이어링과 의존성 주입 (비동기)

`app/` 패키지 밖에서 참고용으로 두는 문서다. API 스택은 **SQLAlchemy 2.0 비동기**(`AsyncSession`, `postgresql+asyncpg`)를 기준으로 한다.

## 레이어 역할

| 레이어 | 책임 |
|--------|------|
| **Route (API)** | HTTP 입출력, 스키마 검증, 상태 코드. 비즈니스 규칙은 두지 않는다. |
| **Service** | 유스케이스, 도메인 규칙, 여러 리포 조합. DB는 리포만 통한다. |
| **Repository** | `AsyncSession`으로 CRUD·조회. `BaseRepo`를 상속해 모델만 고정한다. |
| **Model** | 테이블 매핑. 선언 베이스는 `DeclarativeBase`를 상속한 `app.core.database.Base`를 쓴다. |

데이터 흐름: **Router → Service → Repository → DB**

## DB 세션 (`database.py`)

- 엔진: `async_engine` — `settings.async_database_url` (`postgresql+asyncpg://…`)
- 세션 팩토리: `AsyncSessionLocal` (`async_sessionmaker`)
- 의존성용 제너레이터: `get_async_db_session`  
  - 요청 동안 `yield session`  
  - 정상 종료 시 자동 `commit` 없음 (요청 수명주기에서 커밋하지 않음)  
  - 예외 시 `await session.rollback()`  

마이그레이션·일회성 스크립트 등에서 동기 접속이 필요하면 설정의 `sync_database_url`(`postgresql+psycopg://…`)로 별도 스크립트를 두는 방식이 일반적이다. (앱 런타임 경로와는 분리.)

## 세션 주입 (`deps.py`)

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db_session

DbSessionDep = Annotated[AsyncSession, Depends(get_async_db_session)]
```

라우트나 하위 `Depends` 팩토리에서 `session: DbSessionDep`로 받는다.

## BaseRepo

구현: `app/repositories/BaseRepo.py`

- 생성자: `BaseRepo(session: AsyncSession, model: Type[T])`
- 메서드는 모두 **비동기** (`async def` + 필요 시 `await`):
  - `save`, `save_all`, `get_by_id`, `get_all`, `remove`, `commit`, `rollback`, `flush`

## Repository 예시

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.BaseRepo import BaseRepo
from app.models.user import User  # 프로젝트 모델 경로에 맞게 수정


class UserRepo(BaseRepo[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)
```

## Service 예시

```python
from app.models.user import User
from app.repositories.user_repo import UserRepo


class UserService:
    def __init__(self, repo: UserRepo) -> None:
        self._repo = repo

    async def list_users(self) -> list[User]:
        return await self._repo.get_all()
```

## Depends 체인 예시

FastAPI가 `get_async_db_session` → `UserRepo` → `UserService` 순으로 조립한다.  
`app/core/deps.py`에 두거나, 도메인별로 `app/core/deps_user.py` 등으로 나눠도 된다.

리포/서비스 팩토리는 **`async def`** 로 두는 것이 자연스럽다 (세션이 비동기이므로).

```python
from typing import Annotated

from fastapi import Depends

from app.core.deps import DbSessionDep
from app.repositories.user_repo import UserRepo
from app.services.user_service import UserService


async def get_user_repo(session: DbSessionDep) -> UserRepo:
    return UserRepo(session)


UserRepoDep = Annotated[UserRepo, Depends(get_user_repo)]


async def get_user_service(repo: UserRepoDep) -> UserService:
    return UserService(repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
```

## 라우터 예시

핸들러는 **`async def`** 로 두고, 서비스 메서드는 `await` 한다.

```python
from fastapi import APIRouter

from app.core.deps import UserServiceDep  # 위 예시에서 정의한 경우

router = APIRouter()


@router.get("/users")
async def list_users(svc: UserServiceDep):
    return await svc.list_users()
```

## 트랜잭션·커밋

- 의존성 teardown(`yield` 이후)에서 자동 `commit`하지 않는다.
- 쓰기 유스케이스는 **Service 레이어에서 명시적으로 `commit`** 한다. (예: `await repo.commit()`)
- 이 방식은 응답 반환 이후 `commit` 실패로 인한 데이터 불일치 위험을 줄인다.
- 예외가 나면 의존성 쪽에서 `rollback`이 호출된다.

## API 응답 포맷

- 성공: `isSuccess: true`, `code`, `message`, `result`
- 실패: `isSuccess: false`, `code`, `message`, `result`
- `result`는 실패에서도 오버로딩 개념처럼 사용한다.
  - 기본 실패는 `result: null`
  - 상세 에러 데이터가 필요하면 `result`에 객체를 담아 반환한다.

## 다른 백엔드(Spring 등)와 DB 공유

- DB 서버는 클라이언트가 동기/비동기인지 구분하지 않는다. **같은 PostgreSQL을 Spring(JDBC)과 이 서비스(asyncpg)가 같이 쓰는 구성은 문제 없다.**
- 합쳐진 커넥션 풀 크기·스키마 마이그레이션·동시 쓰기 규칙만 맞추면 된다.

## 관련 파일

- DB 엔진·세션: `app/core/database.py` (`async_engine`, `AsyncSessionLocal`, `get_async_db_session`)
- 세션 DI: `app/core/deps.py` (`DbSessionDep`)
- 코어 re-export: `app/core/__init__.py`
- 리포 베이스: `app/repositories/BaseRepo.py`
- 설정 URL: `app/core/config.py` (`async_database_url`, `sync_database_url`)
