from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

ENDPOINT_SEARCH_FESTIVAL = "searchFestival2"
ENDPOINT_DETAIL_COMMON = "detailCommon2"
ENDPOINT_DETAIL_INTRO = "detailIntro2"
ENDPOINT_DETAIL_IMAGE = "detailImage2"
ENDPOINT_DETAIL_PET_TOUR = "detailPetTour2"


class VisitKoreaClient:
    # 한국관광공사 국문 관광정보 OpenAPI (공공데이터포털) HTTP 클라이언트

    def __init__(
        self,
        *,
        service_key: str,
        base_url: str = settings.visitkorea_api_base_url,
        mobile_os: str = settings.visitkorea_mobile_os,
        mobile_app: str = settings.visitkorea_mobile_app,
        timeout_seconds: float = settings.visitkorea_request_timeout_seconds,
        request_interval_seconds: float = settings.visitkorea_request_interval_seconds,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._service_key = service_key
        self._base_url = base_url.rstrip("/")
        self._mobile_os = mobile_os
        self._mobile_app = mobile_app
        self._timeout = timeout_seconds
        self._interval = max(0.0, request_interval_seconds)
        self._http = http_client
        self._owns_client = http_client is None
        self._request_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, cfg: Settings | None = None) -> VisitKoreaClient:
        s = cfg or settings
        secret = s.visitkorea_service_key
        if secret is None:
            raise RuntimeError("VISITKOREA_SERVICE_KEY가 설정되어 있지 않습니다.")
        return cls(
            service_key=secret.get_secret_value(),
            base_url=s.visitkorea_api_base_url,
            mobile_os=s.visitkorea_mobile_os,
            mobile_app=s.visitkorea_mobile_app,
            timeout_seconds=s.visitkorea_request_timeout_seconds,
            request_interval_seconds=s.visitkorea_request_interval_seconds,
        )

    async def __aenter__(self) -> VisitKoreaClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()

    def _common_params(self, **extra: Any) -> dict[str, str]:
        params: dict[str, str] = {
            "serviceKey": self._service_key,
            "MobileOS": self._mobile_os,
            "MobileApp": self._mobile_app,
            "_type": "json",
            "numOfRows": str(extra.pop("numOfRows", 100)),
            "pageNo": str(extra.pop("pageNo", 1)),
        }
        for key, value in extra.items():
            if value is None:
                continue
            params[key] = str(value)
        return params

    async def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        if self._http is None:
            raise RuntimeError("VisitKoreaClient is not started; use async with VisitKoreaClient.from_settings()")
        query = urlencode(self._common_params(**params))
        url = f"{self._base_url}/{endpoint}?{query}"
        async with self._request_lock:
            response = await self._http.get(url)
            response.raise_for_status()
            payload = response.json()
            if self._interval > 0:
                await asyncio.sleep(self._interval)
        return payload

    async def search_festival(
        self,
        *,
        event_start_date: str,
        event_end_date: str | None = None,
        page_no: int = 1,
        num_of_rows: int = 100,
    ) -> dict[str, Any]:
        # 기간만으로 전국 수집. 근접 필터는 백엔드 longitude/latitude
        return await self._get(
            ENDPOINT_SEARCH_FESTIVAL,
            eventStartDate=event_start_date,
            eventEndDate=event_end_date or event_start_date,
            pageNo=page_no,
            numOfRows=num_of_rows,
        )

    async def detail_common(self, *, content_id: str) -> dict[str, Any]:
        # KorService2 GW: contentId만
        return await self._get(
            ENDPOINT_DETAIL_COMMON,
            contentId=content_id,
            numOfRows=1,
            pageNo=1,
        )

    async def detail_intro(self, *, content_id: str, content_type_id: str) -> dict[str, Any]:
        return await self._get(
            ENDPOINT_DETAIL_INTRO,
            contentId=content_id,
            contentTypeId=content_type_id,
            numOfRows=100,
            pageNo=1,
        )

    async def detail_image(self, *, content_id: str) -> dict[str, Any]:
        return await self._get(
            ENDPOINT_DETAIL_IMAGE,
            contentId=content_id,
            numOfRows=50,
            pageNo=1,
        )

    async def detail_pet_tour(self, *, content_id: str) -> dict[str, Any]:
        return await self._get(
            ENDPOINT_DETAIL_PET_TOUR,
            contentId=content_id,
            numOfRows=1,
            pageNo=1,
        )
