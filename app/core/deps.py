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
from app.repositories.CardnewsImageS3Repo import CardnewsImageS3Repo
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.ComplaintPetitionRepo import ComplaintPetitionRepo
from app.repositories.DepartmentRepo import DepartmentRepo
from app.repositories.EventPinRepo import EventPinRepo
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.LocationDepartmentRepo import LocationDepartmentRepo
from app.repositories.LocationRepo import LocationRepo
from app.repositories.PinLikeRepo import PinLikeRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinLocationRepo import PinLocationRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.services.IssueService import IssueService
from app.services.internal.IssuePinDailyRateLimitService import IssuePinDailyRateLimitService
from app.services.internal.IssuePinBackgroundRunner import IssuePinBackgroundRunner
from app.services.UserService import UserService
from app.services.ComplaintEmailService import ComplaintEmailService
from app.services.ContestPinService import ContestPinService
from app.services.ContestEventIngestService import ContestEventIngestService
from app.services.FestivalPinService import FestivalPinService
from app.services.PolicyEventIngestService import PolicyEventIngestService
from app.services.PolicyPinService import PolicyPinService
from app.services.internal.ContestPinSchedulerService import ContestPinSchedulerService
from app.services.internal.PolicyPinSchedulerService import PolicyPinSchedulerService
from app.services.ComplaintPetitionService import ComplaintPetitionService
from app.services.FestivalEventIngestService import FestivalEventIngestService
from app.services.VectorStoreService import VectorStoreService
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.internal.ai.VLMService import VLMService
from app.services.internal.ai.gemini_factory import (
    build_issue_pin_llm_service,
    build_issue_rag_planner_service,
    build_vlm_service,
    require_gemini_api_key,
)
from app.services.internal.complaint_wiring import build_complaint_email_service
from app.services.internal.geo.ImageExifLocationResolveService import ImageExifLocationResolveService
from app.services.internal.geo.ImageMultipartGeoService import ImageMultipartGeoService
from app.services.internal.geo.LocationResolveClient import LocationResolveClient
from app.utils.S3Util import S3Util
from app.models.enum.UserRole import UserRole


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
    return build_vlm_service()


VLMServiceDep = Annotated[VLMService, Depends(get_vlm_service)]


def get_issue_pin_llm_service() -> IssuePinLLMService:
    try:
        return build_issue_pin_llm_service()
    except RuntimeError:
        raise_business_exception(ErrorCode.VLM_NOT_CONFIGURED)


IssuePinLLMServiceDep = Annotated[IssuePinLLMService, Depends(get_issue_pin_llm_service)]


def get_issue_rag_planner_service() -> IssueRagPlannerService:
    return build_issue_rag_planner_service()


IssueRagPlannerServiceDep = Annotated[
    IssueRagPlannerService,
    Depends(get_issue_rag_planner_service),
]


def get_vector_store_service(request: Request) -> VectorStoreService:
    vector_store_service = getattr(request.app.state, "vector_store_service", None)
    if vector_store_service is None:
        raise RuntimeError("VectorStoreService is not initialized. Check application lifespan setup.")
    return vector_store_service


VectorStoreServiceDep = Annotated[VectorStoreService, Depends(get_vector_store_service)]


def get_pin_repo(session: DbSessionDep) -> PinRepo:
    return PinRepo(session)


PinRepoDep = Annotated[PinRepo, Depends(get_pin_repo)]


def get_issue_pin_repo(session: DbSessionDep) -> IssuePinRepo:
    return IssuePinRepo(session)


IssuePinRepoDep = Annotated[IssuePinRepo, Depends(get_issue_pin_repo)]


def get_pin_location_repo(session: DbSessionDep) -> PinLocationRepo:
    return PinLocationRepo(session)


PinLocationRepoDep = Annotated[PinLocationRepo, Depends(get_pin_location_repo)]


def get_pin_image_repo(session: DbSessionDep) -> PinImageRepo:
    return PinImageRepo(session)


PinImageRepoDep = Annotated[PinImageRepo, Depends(get_pin_image_repo)]


def get_pin_like_repo(session: DbSessionDep) -> PinLikeRepo:
    return PinLikeRepo(session)


PinLikeRepoDep = Annotated[PinLikeRepo, Depends(get_pin_like_repo)]


def get_community_repo(session: DbSessionDep) -> CommunityRepo:
    return CommunityRepo(session)


CommunityRepoDep = Annotated[CommunityRepo, Depends(get_community_repo)]


def get_department_repo(session: DbSessionDep) -> DepartmentRepo:
    return DepartmentRepo(session)


DepartmentRepoDep = Annotated[DepartmentRepo, Depends(get_department_repo)]


def get_location_repo(session: DbSessionDep) -> LocationRepo:
    return LocationRepo(session)


LocationRepoDep = Annotated[LocationRepo, Depends(get_location_repo)]


def get_location_department_repo(session: DbSessionDep) -> LocationDepartmentRepo:
    return LocationDepartmentRepo(session)


LocationDepartmentRepoDep = Annotated[LocationDepartmentRepo, Depends(get_location_department_repo)]


def get_complaint_petition_repo(session: DbSessionDep) -> ComplaintPetitionRepo:
    return ComplaintPetitionRepo(session)


ComplaintPetitionRepoDep = Annotated[ComplaintPetitionRepo, Depends(get_complaint_petition_repo)]


def get_complaint_email_service(
    vector_store_service: VectorStoreServiceDep,
) -> ComplaintEmailService:
    return build_complaint_email_service(
        api_key=require_gemini_api_key(),
        vector_store_service=vector_store_service,
    )


ComplaintEmailServiceDep = Annotated[ComplaintEmailService, Depends(get_complaint_email_service)]


def get_s3_util(request: Request) -> S3Util:
    s3_util = getattr(request.app.state, "s3_util", None)
    if s3_util is None:
        raise RuntimeError("S3Util is not initialized. Check application lifespan setup.")
    return s3_util


S3UtilDep = Annotated[S3Util, Depends(get_s3_util)]


def get_complaint_petition_service(
    complaint_email_service: ComplaintEmailServiceDep,
    issue_pin_repo: IssuePinRepoDep,
    location_department_repo: LocationDepartmentRepoDep,
    complaint_petition_repo: ComplaintPetitionRepoDep,
    department_repo: DepartmentRepoDep,
    location_repo: LocationRepoDep,
    user_repo: UserRepoDep,
    s3_util: S3UtilDep,
) -> ComplaintPetitionService:
    return ComplaintPetitionService(
        complaint_email_service=complaint_email_service,
        issue_pin_repo=issue_pin_repo,
        location_department_repo=location_department_repo,
        complaint_petition_repo=complaint_petition_repo,
        department_repo=department_repo,
        location_repo=location_repo,
        user_repo=user_repo,
        s3_util=s3_util,
    )


ComplaintPetitionServiceDep = Annotated[ComplaintPetitionService, Depends(get_complaint_petition_service)]


def get_issue_pin_background_runner(
    request: Request,
    vlm_service: VLMServiceDep,
    exif_location_service: ImageExifLocationResolveServiceDep,
    s3_util: S3UtilDep,
    issue_rag_planner_service: IssueRagPlannerServiceDep,
) -> IssuePinBackgroundRunner:
    vector_store_service = getattr(request.app.state, "vector_store_service", None)
    redis_client = getattr(request.app.state, "async_redis_client", None)
    return IssuePinBackgroundRunner(
        vlm_service=vlm_service,
        exif_location_service=exif_location_service,
        s3_util=s3_util,
        vector_store_service=vector_store_service,
        issue_rag_planner_service=issue_rag_planner_service,
        redis_client=redis_client,
    )


IssuePinBackgroundRunnerDep = Annotated[
    IssuePinBackgroundRunner,
    Depends(get_issue_pin_background_runner),
]


def get_issue_pin_daily_rate_limit_service(request: Request) -> IssuePinDailyRateLimitService:
    redis_client = getattr(request.app.state, "async_redis_client", None)
    return IssuePinDailyRateLimitService(redis_client=redis_client)


IssuePinDailyRateLimitServiceDep = Annotated[
    IssuePinDailyRateLimitService,
    Depends(get_issue_pin_daily_rate_limit_service),
]


def get_issue_service(
    vector_store_service: VectorStoreServiceDep,
    issue_rag_planner_service: IssueRagPlannerServiceDep,
    location_resolve_client: LocationResolveClientDep,
    issue_pin_llm_service: IssuePinLLMServiceDep,
    pin_repo: PinRepoDep,
    issue_pin_repo: IssuePinRepoDep,
    pin_location_repo: PinLocationRepoDep,
    pin_image_repo: PinImageRepoDep,
    pin_like_repo: PinLikeRepoDep,
    community_repo: CommunityRepoDep,
    user_repo: UserRepoDep,
    s3_util: S3UtilDep,
    background_runner: IssuePinBackgroundRunnerDep,
    issue_pin_daily_rate_limit_service: IssuePinDailyRateLimitServiceDep,
) -> IssueService:
    return IssueService(
        vector_store_service=vector_store_service,
        issue_rag_planner_service=issue_rag_planner_service,
        location_resolve_client=location_resolve_client,
        issue_pin_llm_service=issue_pin_llm_service,
        pin_repo=pin_repo,
        issue_pin_repo=issue_pin_repo,
        pin_location_repo=pin_location_repo,
        pin_image_repo=pin_image_repo,
        pin_like_repo=pin_like_repo,
        community_repo=community_repo,
        user_repo=user_repo,
        s3_util=s3_util,
        background_runner=background_runner,
        issue_pin_daily_rate_limit_service=issue_pin_daily_rate_limit_service,
    )


IssueServiceDep = Annotated[IssueService, Depends(get_issue_service)]


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


async def require_admin_uid(
    uid: CurrentUserIdDep,
    user_repo: UserRepoDep,
) -> str:
    user = await user_repo.get_by_uid(uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN role required",
        )
    return uid


AdminUserIdDep = Annotated[str, Depends(require_admin_uid)]


def get_festival_pin_service() -> FestivalPinService:
    return FestivalPinService()


FestivalPinServiceDep = Annotated[
    FestivalPinService,
    Depends(get_festival_pin_service),
]


def get_event_pin_repo(session: DbSessionDep) -> EventPinRepo:
    return EventPinRepo(session)


EventPinRepoDep = Annotated[EventPinRepo, Depends(get_event_pin_repo)]


def get_festival_event_ingest_service(
    pin_repo: PinRepoDep,
    event_pin_repo: EventPinRepoDep,
    pin_location_repo: PinLocationRepoDep,
    pin_image_repo: PinImageRepoDep,
    location_resolve_client: LocationResolveClientDep,
) -> FestivalEventIngestService:
    return FestivalEventIngestService(
        pin_repo=pin_repo,
        event_pin_repo=event_pin_repo,
        pin_location_repo=pin_location_repo,
        pin_image_repo=pin_image_repo,
        location_resolve_client=location_resolve_client,
    )


FestivalEventIngestServiceDep = Annotated[
    FestivalEventIngestService,
    Depends(get_festival_event_ingest_service),
]


def get_contest_pin_service() -> ContestPinService:
    return ContestPinService()


ContestPinServiceDep = Annotated[
    ContestPinService,
    Depends(get_contest_pin_service),
]


def get_policy_pin_service() -> PolicyPinService:
    return PolicyPinService()


PolicyPinServiceDep = Annotated[
    PolicyPinService,
    Depends(get_policy_pin_service),
]


def get_cardnews_image_s3_repo(session: DbSessionDep) -> CardnewsImageS3Repo:
    return CardnewsImageS3Repo(session)


CardnewsImageS3RepoDep = Annotated[CardnewsImageS3Repo, Depends(get_cardnews_image_s3_repo)]


def get_policy_event_ingest_service(
    pin_repo: PinRepoDep,
    event_pin_repo: EventPinRepoDep,
    community_repo: CommunityRepoDep,
    cardnews_image_s3_repo: CardnewsImageS3RepoDep,
    user_repo: UserRepoDep,
) -> PolicyEventIngestService:
    return PolicyEventIngestService(
        pin_repo=pin_repo,
        event_pin_repo=event_pin_repo,
        community_repo=community_repo,
        cardnews_image_s3_repo=cardnews_image_s3_repo,
        user_repo=user_repo,
    )


PolicyEventIngestServiceDep = Annotated[
    PolicyEventIngestService,
    Depends(get_policy_event_ingest_service),
]


def get_policy_pin_scheduler(request: Request) -> PolicyPinSchedulerService | None:
    scheduler = getattr(request.app.state, "policy_pin_scheduler", None)
    if scheduler is None:
        return None
    if not isinstance(scheduler, PolicyPinSchedulerService):
        raise RuntimeError("policy_pin_scheduler is not initialized correctly.")
    return scheduler


PolicyPinSchedulerDep = Annotated[
    PolicyPinSchedulerService | None,
    Depends(get_policy_pin_scheduler),
]


def get_contest_event_ingest_service(
    pin_repo: PinRepoDep,
    event_pin_repo: EventPinRepoDep,
    community_repo: CommunityRepoDep,
    cardnews_image_s3_repo: CardnewsImageS3RepoDep,
    pin_image_repo: PinImageRepoDep,
    user_repo: UserRepoDep,
) -> ContestEventIngestService:
    return ContestEventIngestService(
        pin_repo=pin_repo,
        event_pin_repo=event_pin_repo,
        community_repo=community_repo,
        cardnews_image_s3_repo=cardnews_image_s3_repo,
        pin_image_repo=pin_image_repo,
        user_repo=user_repo,
    )


ContestEventIngestServiceDep = Annotated[
    ContestEventIngestService,
    Depends(get_contest_event_ingest_service),
]


def get_contest_pin_scheduler(request: Request) -> ContestPinSchedulerService | None:
    scheduler = getattr(request.app.state, "contest_pin_scheduler", None)
    if scheduler is None:
        return None
    if not isinstance(scheduler, ContestPinSchedulerService):
        raise RuntimeError("contest_pin_scheduler is not initialized correctly.")
    return scheduler


ContestPinSchedulerDep = Annotated[
    ContestPinSchedulerService | None,
    Depends(get_contest_pin_scheduler),
]
