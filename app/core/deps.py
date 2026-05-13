from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.codes import ErrorCode
from app.core.config import settings
from app.core.database import get_async_db_session
from app.core.exceptions import raise_business_exception
from app.login.http_auth import get_current_user_id, get_optional_user_id
from app.models.User import User
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.services.IssuePinLLMService import IssuePinLLMService
from app.services.IssueService import IssueService
from app.services.ImageExifLocationResolveService import ImageExifLocationResolveService
from app.services.ImageMultipartGeoService import ImageMultipartGeoService
from app.services.LocationResolveClient import LocationResolveClient
from app.services.UserService import UserService
from app.services.VLMService import VLMService
from app.services.VectorStoreService import VectorStoreService
from app.utils.S3Util import S3Util


DbSessionDep = Annotated[AsyncSession, Depends(get_async_db_session)]


def get_user_repo(session: DbSessionDep) -> UserRepo:
    return UserRepo(session)


UserRepoDep = Annotated[UserRepo, Depends(get_user_repo)]


def get_user_service(user_repo: UserRepoDep) -> UserService:
    return UserService(user_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_image_multipart_geo_service() -> ImageMultipartGeoService:
    return ImageMultipartGeoService()


ImageMultipartGeoServiceDep = Annotated[
    ImageMultipartGeoService,
    Depends(get_image_multipart_geo_service),
]


def get_location_resolve_client(request: Request) -> LocationResolveClient:
    http_client = getattr(request.app.state, "shared_httpx_client", None)
    if http_client is None or not isinstance(http_client, httpx.AsyncClient):
        raise RuntimeError(
            "shared_httpx_client is not initialized. Check FastAPI lifespan in app.main.",
        )
    return LocationResolveClient(
        http_client=http_client,
        base_url=settings.location_core_base_url,
    )


LocationResolveClientDep = Annotated[LocationResolveClient, Depends(get_location_resolve_client)]


def get_image_exif_location_resolve_service(
    multipart_geo: ImageMultipartGeoServiceDep,
    location_resolve: LocationResolveClientDep,
) -> ImageExifLocationResolveService:
    return ImageExifLocationResolveService(multipart_geo, location_resolve)


ImageExifLocationResolveServiceDep = Annotated[
    ImageExifLocationResolveService,
    Depends(get_image_exif_location_resolve_service),
]


def get_vlm_service() -> VLMService:
    api_key_secret = settings.gemini_api_key
    if api_key_secret is None:
        raise_business_exception(ErrorCode.VLM_NOT_CONFIGURED)
    return VLMService(
        api_key=api_key_secret.get_secret_value(),
        model_name=settings.gemini_vlm_model,
    )


VLMServiceDep = Annotated[VLMService, Depends(get_vlm_service)]


def get_issue_pin_llm_service() -> IssuePinLLMService:
    api_key_secret = settings.gemini_api_key
    if api_key_secret is None:
        raise_business_exception(ErrorCode.VLM_NOT_CONFIGURED)
    return IssuePinLLMService(
        api_key=api_key_secret.get_secret_value(),
        model_name=settings.gemini_pin_text_model,
    )


IssuePinLLMServiceDep = Annotated[IssuePinLLMService, Depends(get_issue_pin_llm_service)]


def get_vector_store_service(request: Request) -> VectorStoreService:
    vector_store_service = getattr(request.app.state, "vector_store_service", None)
    if vector_store_service is None:
        raise RuntimeError("VectorStoreService is not initialized. Check application lifespan setup.")
    return vector_store_service


VectorStoreServiceDep = Annotated[VectorStoreService, Depends(get_vector_store_service)]


def get_image_multipart_geo_service() -> ImageMultipartGeoService:
    return ImageMultipartGeoService()


ImageMultipartGeoServiceDep = Annotated[
    ImageMultipartGeoService,
    Depends(get_image_multipart_geo_service),
]


def get_location_resolve_client(request: Request) -> LocationResolveClient:
    http_client = getattr(request.app.state, "shared_httpx_client", None)
    if http_client is None or not isinstance(http_client, httpx.AsyncClient):
        raise RuntimeError(
            "shared_httpx_client is not initialized. Check FastAPI lifespan in app.main.",
        )
    return LocationResolveClient(
        http_client=http_client,
        base_url=settings.location_core_base_url,
    )


LocationResolveClientDep = Annotated[LocationResolveClient, Depends(get_location_resolve_client)]


def get_image_exif_location_resolve_service(
    multipart_geo: ImageMultipartGeoServiceDep,
    location_resolve: LocationResolveClientDep,
) -> ImageExifLocationResolveService:
    return ImageExifLocationResolveService(multipart_geo, location_resolve)


ImageExifLocationResolveServiceDep = Annotated[
    ImageExifLocationResolveService,
    Depends(get_image_exif_location_resolve_service),
]


def get_pin_repo(session: DbSessionDep) -> PinRepo:
    return PinRepo(session)


PinRepoDep = Annotated[PinRepo, Depends(get_pin_repo)]


def get_issue_pin_repo(session: DbSessionDep) -> IssuePinRepo:
    return IssuePinRepo(session)


IssuePinRepoDep = Annotated[IssuePinRepo, Depends(get_issue_pin_repo)]


def get_issue_service(
    vector_store_service: VectorStoreServiceDep,
    vlm_service: VLMServiceDep,
    image_exif_location_resolve_service: ImageExifLocationResolveServiceDep,
    issue_pin_llm_service: IssuePinLLMServiceDep,
    pin_repo: PinRepoDep,
    issue_pin_repo: IssuePinRepoDep,
    user_repo: UserRepoDep,
) -> IssueService:
    return IssueService(
        vector_store_service=vector_store_service,
        vlm_service=vlm_service,
        image_exif_location_resolve_service=image_exif_location_resolve_service,
        issue_pin_llm_service=issue_pin_llm_service,
        pin_repo=pin_repo,
        issue_pin_repo=issue_pin_repo,
        user_repo=user_repo,
    )


IssueServiceDep = Annotated[IssueService, Depends(get_issue_service)]


def get_s3_util(request: Request) -> S3Util:
    s3_util = getattr(request.app.state, "s3_util", None)
    if s3_util is None:
        raise RuntimeError("S3Util is not initialized. Check application lifespan setup.")
    return s3_util


S3UtilDep = Annotated[S3Util, Depends(get_s3_util)]


def get_async_redis_client(request: Request) -> AsyncRedis:
    redis_client = getattr(request.app.state, "async_redis_client", None)
    if redis_client is None:
        raise RuntimeError("Async Redis client is not initialized. Check application lifespan setup.")
    return redis_client


AsyncRedisDep = Annotated[AsyncRedis, Depends(get_async_redis_client)]

CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]
OptionalUserIdDep = Annotated[str | None, Depends(get_optional_user_id)]


async def get_current_user(
    uid: CurrentUserIdDep,
    user_repo: UserRepoDep,
) -> User:
    u = await user_repo.get_by_uid(uid)
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return u


CurrentUserDep = Annotated[User, Depends(get_current_user)]
