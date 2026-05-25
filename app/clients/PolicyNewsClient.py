from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, settings
from app.utils.policy_news_parse import parse_policy_news_xml, policy_result_ok

logger = logging.getLogger(__name__)

ENDPOINT_POLICY_NEWS_LIST = "policyNewsList"

class PolicyNewsClient:
    # 문화체육관광부 정책브리핑 정책뉴스 OpenAPI (공공데이터포털)

    def __init__(
        self,
        *,
        service_key: str,
        base_url: str = settings.policy_news_api_base_url,
        timeout_seconds: float = settings.policy_news_request_timeout_seconds,
        request_interval_seconds: float = settings.policy_news_request_interval_seconds,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._service_key = service_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._interval = max(0.0, request_interval_seconds)
        self._http = http_client
        self._owns_client = http_client is None

    @classmethod
    def from_settings(cls, config: Settings | None = None) -> PolicyNewsClient:
        s = config or settings
        secret = s.policy_news_service_key
        if secret is None:
            raise RuntimeError(
                "POLICY_NEWS_SERVICE_KEY가 설정되어 있지 않습니다.",
            )
        return cls(
            service_key=secret.get_secret_value(),
            base_url=s.policy_news_api_base_url,
            timeout_seconds=s.policy_news_request_timeout_seconds,
            request_interval_seconds=s.policy_news_request_interval_seconds,
        )

    async def __aenter__(self) -> PolicyNewsClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()

    async def _get_xml(self, endpoint: str, **params: Any) -> str:
        if self._http is None:
            raise RuntimeError(
                "PolicyNewsClient is not started; use async with PolicyNewsClient.from_settings()",
            )
        query_params = {
            "serviceKey": self._service_key,
            **{k: str(v) for k, v in params.items() if v is not None},
        }
        query = urlencode(query_params)
        url = f"{self._base_url}/{endpoint}?{query}"
        response = await self._http.get(url)
        response.raise_for_status()
        if self._interval > 0:
            await asyncio.sleep(self._interval)
        return response.text

    async def policy_news_list(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> tuple[dict[str, str], list[dict[str, str]]]:
        xml_text = await self._get_xml(
            ENDPOINT_POLICY_NEWS_LIST,
            startDate=start_date,
            endDate=end_date,
        )
        header, items = parse_policy_news_xml(xml_text)
        ok, msg = policy_result_ok(header)
        if not ok:
            raise RuntimeError(f"policyNewsList 실패 ({start_date}~{end_date}): {msg}")
        return header, items
