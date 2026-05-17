from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any

from google import genai
from google.genai import types
from starlette.datastructures import UploadFile

from app.schemas.ComplaintEmailDTO import (
    ComplaintEmailVlmAnalyzeResult,
    ComplaintEmailVlmImageSlot,
    ComplaintEmailVlmInput,
    ComplaintEmailVlmOutput,
)
from app.schemas.IssueDTO import ImageWithLocation
from app.services.ComplaintEmailVlm_prompt import (
    ComplaintEmailVlmCatalog,
    ComplaintEmailVlmPromptBuilder,
)


class ComplaintEmailVlmResultProcessor:
    """VLM JSON 파싱·enum 보정·error_code·검색어 후처리."""

    _LOCATION_VERIFICATION_MESSAGES: dict[str, str] = {
        "matched": "사용자 위치와 사진 메타데이터 위치가 일치합니다",
        "same_area": "사용자 위치와 사진 메타데이터 위치가 같은 동네 수준으로 보입니다",
        "different_area": "사용자 위치와 사진 메타데이터 위치가 다를 수 있습니다",
        "not_checked": "메타데이터에 주소가 없습니다",
        "unknown": "위치 일치 여부를 판단하기 어렵습니다",
    }

    _LOCATION_MISMATCH_RISK = "사용자 위치와 사진 메타데이터 주소가 다를 수 있음"

    _LOCATION_PATTERN = re.compile(
        r"[가-힣0-9]+(?:특별자치도|특별자치시|특별시|광역시)(?:\s*[,\s]|$)+|"
        r"[가-힣0-9]+(?:시|군)(?:\s*[,\s]|$)+|"
        r"[가-힣0-9]+구(?:\s*[,\s]|$)+|"
        r"[가-힣0-9]+(?:읍|면|동|리)(?:\s*[,\s]|$)+"
    )

    _PURE_ADMIN_KEYWORD = re.compile(
        r"^[가-힣0-9]+(?:특별자치도|특별자치시|특별시|광역시|시|군|구|읍|면|동|리)$"
    )

    _PRIVACY_HINTS: tuple[str, ...] = ("번호판", "얼굴", "안면", "차량번호", "신분증")

    def __init__(self, catalog: type[ComplaintEmailVlmCatalog] = ComplaintEmailVlmCatalog) -> None:
        self._catalog = catalog

    def parse_model_output(self, parsed: dict[str, Any]) -> ComplaintEmailVlmOutput:
        category_type, domain = self._normalize_type_and_domain(
            raw_type=parsed.get("type"),
            raw_domain=parsed.get("domain"),
        )
        cat = self._catalog

        subcategory = parsed.get("subcategory")
        sub: str | None
        if isinstance(subcategory, str) and subcategory.strip():
            sub = subcategory.strip()
        else:
            sub = cat.DEFAULT_SUBCATEGORY

        summary = parsed.get("summary")
        summary_s = summary.strip() if isinstance(summary, str) else ""

        objects_raw = parsed.get("objects")
        objects = (
            [o.strip() for o in objects_raw if isinstance(o, str) and o.strip()]
            if isinstance(objects_raw, list)
            else []
        )

        return ComplaintEmailVlmOutput(
            type=category_type,
            domain=domain,
            subcategory=sub,
            summary=summary_s,
            objects=objects,
            error_code=self._parse_vlm_error_code(parsed.get("error_code")),
            keywords=self._normalize_keywords(parsed.get("keywords")),
            query=self._parse_query(parsed.get("query")),
        )

    def normalize_model_output(
        self,
        model: ComplaintEmailVlmOutput,
        *,
        user_location: str | None,
        photo_address: str | None,
    ) -> ComplaintEmailVlmAnalyzeResult:
        query = model.query
        keywords = list(model.keywords)

        if user_location is None and photo_address is None:
            query = self._clean_location_query(query, location_context=None)
            keywords = self._clean_location_keywords(keywords, location_context=None)

        error_code = self._resolve_error_code(
            model=model,
            vlm_error_code=model.error_code,
            user_location=user_location,
            photo_address=photo_address,
        )

        return ComplaintEmailVlmAnalyzeResult(
            type=model.type,
            domain=model.domain,
            subcategory=model.subcategory,
            summary=model.summary,
            objects=model.objects,
            error_code=error_code,
            keywords=keywords,
            query=query,
        )

    def build_legacy_context(
        self,
        result: ComplaintEmailVlmAnalyzeResult,
        *,
        user_location: str | None,
        photo_address: str | None,
    ) -> dict[str, Any]:
        location_verification = self._build_location_verification(
            user_location=user_location,
            photo_address=photo_address,
        )
        legacy = result.to_legacy_dict(
            user_location=user_location,
            photo_address=photo_address,
            location_verification=location_verification,
        )
        legacy["confidence_score"] = self._compute_confidence_score(
            result=result,
            location_status=location_verification["status"],
        )
        if location_verification["status"] == "different_area":
            legacy["risk_note"] = self._LOCATION_MISMATCH_RISK
        elif photo_address is None:
            legacy["risk_note"] = "메타데이터에 주소가 없습니다"
        return legacy

    @staticmethod
    def coerce_photo_address(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            s = value.strip()
            return s or None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            parts: list[str] = []
            for item in value:
                if item is None:
                    continue
                t = str(item).strip()
                if t:
                    parts.append(t)
            if not parts:
                return None
            return ", ".join(parts)
        s = str(value).strip()
        return s or None

    @staticmethod
    def resolve_upload_image_mime(upload: UploadFile) -> str:
        mime = (upload.content_type or "").split(";")[0].strip().lower()
        if not mime:
            guessed, _ = mimetypes.guess_type(upload.filename or "")
            mime = (guessed or "").split(";")[0].strip().lower()
        if not mime:
            raise RuntimeError(
                "업로드 파일의 MIME 타입을 확인할 수 없습니다. "
                "Content-Type을 지정하거나 이미지 확장자가 있는 파일명을 사용하세요.",
            )
        if not mime.startswith("image/"):
            raise RuntimeError(f"이미지 파일만 업로드할 수 있습니다. (받은 MIME: {mime})")
        return mime

    def _parse_vlm_error_code(self, raw: object) -> str | None:
        if not isinstance(raw, str):
            return None
        code = raw.strip()
        if code and code in self._catalog.VLM_ERROR_CODES:
            return code
        return None

    @staticmethod
    def _parse_query(raw: object) -> str:
        return raw.strip() if isinstance(raw, str) else ""

    def _resolve_error_code(
        self,
        *,
        model: ComplaintEmailVlmOutput,
        vlm_error_code: str | None,
        user_location: str | None,
        photo_address: str | None,
    ) -> str | None:
        if vlm_error_code is not None:
            return vlm_error_code

        if self._has_privacy_risk(summary=model.summary, objects=model.objects):
            return "E007_PRIVACY_RISK"

        if user_location and photo_address:
            status = self._compare_addresses(
                user_location=user_location,
                photo_address=photo_address,
            )
            if status == "different_area":
                return "E008_LOCATION_MISMATCH"

        cat = self._catalog
        if not model.summary and not model.objects:
            return "E001_IMAGE_ANALYSIS_FAILED"
        if not model.objects:
            return "E002_OBJECT_NOT_IDENTIFIED"
        if model.type == cat.DEFAULT_TYPE:
            return "E004_CATEGORY_UNCLEAR"
        if not model.query and not model.keywords:
            return "E006_UNVERIFIABLE_CLAIM"
        return None

    def _has_privacy_risk(self, *, summary: str, objects: list[str]) -> bool:
        blob = f"{summary} {' '.join(objects)}"
        return any(hint in blob for hint in self._PRIVACY_HINTS)

    def _normalize_type_and_domain(
        self,
        *,
        raw_type: object,
        raw_domain: object,
    ) -> tuple[str, str]:
        cat = self._catalog
        category_type = (
            raw_type.strip()
            if isinstance(raw_type, str) and raw_type.strip() in cat.CATEGORY_TYPES
            else cat.DEFAULT_TYPE
        )
        fallback_domain = cat.TYPE_DOMAIN_FALLBACK.get(category_type, cat.DEFAULT_DOMAIN)
        if not isinstance(raw_domain, str) or raw_domain.strip() not in cat.ADMIN_DOMAINS:
            return category_type, fallback_domain
        domain = raw_domain.strip()
        plausible = cat.TYPE_PLAUSIBLE_DOMAINS.get(category_type)
        if plausible is not None and domain not in plausible:
            return category_type, fallback_domain
        return category_type, domain

    def _normalize_keywords(self, keywords_raw: object) -> list[str]:
        cat = self._catalog
        keywords: list[str] = []
        if isinstance(keywords_raw, list):
            seen: set[str] = set()
            for item in keywords_raw:
                if not isinstance(item, str):
                    continue
                t = item.strip()
                if t and t not in seen:
                    seen.add(t)
                    keywords.append(t)
        if len(keywords) > cat.KEYWORDS_MAX:
            keywords = keywords[: cat.KEYWORDS_MAX]
        return keywords

    def _build_location_verification(
        self,
        *,
        user_location: str | None,
        photo_address: str | None,
    ) -> dict[str, Any]:
        if photo_address is None:
            status = "not_checked"
        elif user_location is None:
            status = "not_checked"
        else:
            status = self._compare_addresses(
                user_location=user_location,
                photo_address=photo_address,
            )
        return {
            "status": status,
            "message": self._LOCATION_VERIFICATION_MESSAGES.get(
                status,
                self._LOCATION_VERIFICATION_MESSAGES["unknown"],
            ),
            "user_location": user_location,
            "photo_location": None,
            "photo_address": photo_address,
        }

    def _compare_addresses(self, *, user_location: str, photo_address: str) -> str:
        u = user_location.strip()
        p = photo_address.strip()
        if not u or not p:
            return "unknown"
        if u == p or u in p or p in u:
            return "matched"
        u_tokens = self._extract_admin_tokens(u)
        p_tokens = self._extract_admin_tokens(p)
        if u_tokens and p_tokens and u_tokens & p_tokens:
            return "same_area"
        return "different_area"

    def _extract_admin_tokens(self, address: str) -> set[str]:
        tokens: set[str] = set()
        for m in self._LOCATION_PATTERN.finditer(address):
            token = m.group(0).strip(" ,·")
            if token:
                tokens.add(token)
        return tokens

    def _compute_confidence_score(
        self,
        *,
        result: ComplaintEmailVlmAnalyzeResult,
        location_status: str,
    ) -> float:
        if result.error_code is not None:
            return 0.2
        score = 0.5
        if result.summary:
            score += 0.15
        if result.objects:
            score += 0.15
        if len(result.keywords) >= 5:
            score += 0.1
        if location_status == "matched":
            score += 0.1
        elif location_status == "different_area":
            score -= 0.15
        return max(0.0, min(1.0, score))

    def _remove_location_terms(self, text: str) -> str:
        t = text.strip()
        if not t:
            return ""
        prev = None
        while prev != t:
            prev = t
            t = self._LOCATION_PATTERN.sub(" ", t)
        return re.sub(r"\s+", " ", t).strip(" ,·")

    def _clean_location_query(self, query: str, *, location_context: str | None) -> str:
        t = query.strip()
        if not t:
            return ""
        if location_context:
            mc = location_context.strip()
            if mc:
                t = t.replace(mc, " ")
        return self._remove_location_terms(t)

    def _clean_location_keywords(
        self,
        keywords: list[str],
        *,
        location_context: str | None,
    ) -> list[str]:
        mc = (location_context or "").strip()
        out: list[str] = []
        seen: set[str] = set()
        for k in keywords:
            t = k.strip()
            if not t:
                continue
            if mc and mc in t:
                t = t.replace(mc, " ").strip()
            t = self._remove_location_terms(t)
            if not t or self._PURE_ADMIN_KEYWORD.match(t):
                continue
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


@dataclass(slots=True)
class ComplaintEmailVlmService:
    api_key: str
    model_name: str = "gemini-3.1-pro-preview"
    client: genai.Client = field(init=False, repr=False)
    catalog: type[ComplaintEmailVlmCatalog] = ComplaintEmailVlmCatalog
    _prompt_builder: ComplaintEmailVlmPromptBuilder = field(init=False, repr=False)
    _result_processor: ComplaintEmailVlmResultProcessor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)
        self._prompt_builder = ComplaintEmailVlmPromptBuilder(self.catalog)
        self._result_processor = ComplaintEmailVlmResultProcessor(self.catalog)

    async def analyze_image(
        self,
        *,
        user_text: str,
        images: list[ImageWithLocation],
        user_location: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """기존 호출부 호환용. 구조화 결과는 :meth:`analyze` 사용."""
        request = self.build_request(
            user_text=user_text,
            user_location=user_location,
            location=location,
        )
        photo_address, image_slots = await self.prepare_images(images)
        result = await self._call_vlm(
            request=self._finalize_request(
                request,
                photo_address=photo_address,
                image_slots=image_slots,
            ),
            images=images,
        )
        return self._result_processor.build_legacy_context(
            result,
            user_location=request.user_location,
            photo_address=photo_address,
        )

    async def analyze(
        self,
        *,
        request: ComplaintEmailVlmInput,
        images: list[ImageWithLocation],
    ) -> ComplaintEmailVlmAnalyzeResult:
        photo_address, image_slots = await self.prepare_images(images)
        return await self._call_vlm(
            request=self._finalize_request(
                request,
                photo_address=photo_address,
                image_slots=image_slots,
            ),
            images=images,
        )

    def build_request(
        self,
        *,
        user_text: str,
        user_location: str | None,
        location: str | None = None,
    ) -> ComplaintEmailVlmInput:
        eff_user_location = user_location
        if (eff_user_location is None or not str(eff_user_location).strip()) and (
            location is not None and str(location).strip()
        ):
            eff_user_location = location
        return ComplaintEmailVlmInput(
            user_text=user_text,
            user_location=(
                eff_user_location.strip()
                if isinstance(eff_user_location, str) and eff_user_location.strip()
                else None
            ),
        )

    @staticmethod
    def _finalize_request(
        request: ComplaintEmailVlmInput,
        *,
        photo_address: str | None,
        image_slots: list[ComplaintEmailVlmImageSlot],
    ) -> ComplaintEmailVlmInput:
        return request.model_copy(
            update={
                "photo_address": photo_address,
                "image_count": len(image_slots),
                "image_slots": image_slots,
            },
        )

    async def prepare_images(
        self,
        images: list[ImageWithLocation],
    ) -> tuple[str | None, list[ComplaintEmailVlmImageSlot]]:
        if not images:
            raise RuntimeError(
                "이미지는 ImageWithLocation(업로드 파일, 사진 메타 주소) 리스트로 1개 이상 전달해야 합니다.",
            )
        per_address_strings: list[str] = []
        slots: list[ComplaintEmailVlmImageSlot] = []
        for idx, row in enumerate(images, start=1):
            image_bytes = await row.image.read()
            if not image_bytes:
                raise RuntimeError(f"업로드 이미지가 비어 있습니다. (인덱스 {idx})")
            await row.image.seek(0)
            one_addr = self._result_processor.coerce_photo_address(row.address)
            name = row.image.filename or f"image_{idx}"
            slots.append(
                ComplaintEmailVlmImageSlot(
                    index=idx,
                    filename=name,
                    photo_address=one_addr,
                ),
            )
            if one_addr:
                per_address_strings.append(one_addr)
        photo_address = ", ".join(per_address_strings) if per_address_strings else None
        return photo_address, slots

    async def _call_vlm(
        self,
        *,
        request: ComplaintEmailVlmInput,
        images: list[ImageWithLocation],
    ) -> ComplaintEmailVlmAnalyzeResult:
        image_parts = await self._build_image_parts(images)
        prompt = self._prompt_builder.build_from_input(request)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=self.catalog.response_json_schema(),
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[*image_parts, prompt],
            config=config,
        )

        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini VLM 응답 텍스트가 비어 있습니다.")

        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise RuntimeError(f"Gemini JSON 파싱 실패: {exc}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini VLM 응답이 JSON 객체가 아닙니다.")

        model_output = self._result_processor.parse_model_output(parsed)
        return self._result_processor.normalize_model_output(
            model_output,
            user_location=request.user_location,
            photo_address=request.photo_address,
        )

    async def _build_image_parts(self, images: list[ImageWithLocation]) -> list[types.Part]:
        parts: list[types.Part] = []
        for idx, row in enumerate(images, start=1):
            image_bytes = await row.image.read()
            if not image_bytes:
                raise RuntimeError(f"업로드 이미지가 비어 있습니다. (인덱스 {idx})")
            mime = self._result_processor.resolve_upload_image_mime(row.image)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            await row.image.seek(0)
        return parts


# deps·IssueService 등 기존 import 호환
VLMService = ComplaintEmailVlmService
