"""정책 카드뉴스 — 어려운 용어를 쉬운 표현으로 바꾸고 설명란 문구 생성."""

from __future__ import annotations

import re
from typing import Any

# 본문·슬라이드 문구에서 바로 치환 (긴 표현부터 적용)
_TERM_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("개인정보 침해", "내 정보(이름·연락처 등)가 새나는 일"),
    ("개인정보", "내 정보(이름·연락처 등)"),
    ("정보주체", "정보가 있는 본인"),
    ("가명정보", "이름을 바꾼 정보"),
    ("익명정보", "누구인지 알 수 없게 만든 정보"),
    ("처리방침", "개인정보 다루는 규칙"),
    ("동의철회", "동의 취소"),
    ("수집·이용", "모으고 쓰기"),
    ("제3자 제공", "다른 기관에 넘기기"),
    ("위탁", "다른 곳에 맡기기"),
    ("실태조사", "실제로 어떻게 되는지 점검"),
    ("실태 점검", "실제로 어떻게 되는지 점검"),
    ("예방 중심", "미리 막는 것을 우선"),
    ("이행 점검", "약속대로 하는지 확인"),
    ("시행령", "대통령령(세부 규칙)"),
    ("고시", "부처가 정한 세부 기준"),
    ("부칙", "시행 날짜 등 부가 규정"),
    ("시행일", "시작 날짜"),
    ("무주택", "집이 없는"),
    ("차상위계층", "생활이 어려운 가구"),
    ("기초생활수급", "생활비를 국가에서 받는"),
    ("소득기준", "벌어들이는 돈 기준"),
    ("재산기준", "가진 재산 기준"),
    ("신청자격", "신청할 수 있는 조건"),
    ("지원대상", "도움받을 수 있는 사람"),
    ("온라인 접수", "인터넷으로 신청"),
    ("오프라인", "직접 방문·우편"),
    ("공고", "정부·기관 안내"),
    ("보도자료", "언론에 낸 공식 안내"),
)

# 설명란에 넣을 '용어 → 쉬운 말' (본문에 등장할 때만)
_TERM_GUIDE_DEFS: tuple[tuple[str, str, str], ...] = (
    ("개인정보", "개인정보", "이름·연락처처럼 나를 알 수 있는 정보"),
    ("정보주체", "정보주체", "그 정보의 주인(본인)"),
    ("실태조사", "실태조사", "실제로 잘 지키는지 현장에서 확인"),
    ("실태 점검", "실태 점검", "실제로 잘 지키는지 확인"),
    ("예방 중심", "예방 중심", "문제가 생기기 전에 막는 것을 우선"),
    ("위탁", "위탁", "다른 기관에 업무를 맡김"),
    ("제3자 제공", "제3자 제공", "다른 기관·회사에 정보를 넘김"),
    ("무주택", "무주택", "본인·가족 명의 집이 없음"),
    ("차상위", "차상위", "생활이 어려운 가구"),
    ("기초생활", "기초생활", "생활비를 국가에서 지원받는 경우"),
    ("소득·재산", "소득·재산", "벌어들이는 돈과 가진 재산"),
    ("시행령", "시행령", "법을 실행하기 위한 대통령령"),
    ("가명정보", "가명정보", "이름 등을 바꿔 놓은 정보"),
)

_GUIDE_LABEL_MARKERS = ("쉬운말", "쉬운 말", "용어", "알아두기", "설명")


def simplify_policy_text(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    for src, dst in _TERM_REPLACEMENTS:
        if src in value:
            value = value.replace(src, dst)
    return re.sub(r"\s{2,}", " ", value).strip()


def extract_term_guides(*texts: str, max_items: int = 3) -> list[str]:
    # 본문에서 찾은 어려운 용어에 대한 짧은 설명 줄
    blob = " ".join(t for t in texts if (t or "").strip())
    if not blob:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for needle, label, plain in _TERM_GUIDE_DEFS:
        if needle not in blob and label not in blob:
            continue
        key = label
        if key in seen:
            continue
        seen.add(key)
        found.append(f"{label} → {plain}")
        if len(found) >= max_items:
            break
    return found


def _simplify_item(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        return {
            "label": simplify_policy_text(str(item.get("label") or "")),
            "text": simplify_policy_text(str(item.get("text") or "")),
        }
    text = simplify_policy_text(str(item))
    return {"label": "", "text": text}


def apply_terms_to_slide(slide: dict[str, Any]) -> dict[str, Any]:
    row = dict(slide)
    for key in ("eyebrow", "headline", "highlight", "subtext", "body", "cta", "speech"):
        row[key] = simplify_policy_text(str(row.get(key) or ""))

    items = [_simplify_item(i) for i in list(row.get("items") or []) if isinstance(i, (dict, str))]
    row["items"] = [i for i in items if str(i.get("text") or "").strip()]

    raw_guides = row.get("term_guides")
    guides: list[str] = []
    if isinstance(raw_guides, list):
        for entry in raw_guides:
            if isinstance(entry, dict):
                term = simplify_policy_text(str(entry.get("term") or entry.get("label") or ""))
                plain = simplify_policy_text(str(entry.get("plain") or entry.get("text") or ""))
                if term and plain:
                    guides.append(f"{term} → {plain}")
            else:
                line = simplify_policy_text(str(entry))
                if line:
                    guides.append(line)
    row["term_guides"] = guides[:3]
    return row


def enrich_cardnews_terminology(
    slides: list[dict[str, Any]],
    *,
    pin_content: str = "",
) -> list[dict[str, Any]]:
    # 슬라이드 문구 쉬운 표현화 + 마무리 슬라이드에 용어 설명란
    if not slides:
        return []

    blob_parts = [pin_content]
    enriched: list[dict[str, Any]] = []
    for slide in slides:
        row = apply_terms_to_slide(slide)
        for key in ("eyebrow", "headline", "highlight", "body", "cta"):
            blob_parts.append(str(row.get(key) or ""))
        for item in row.get("items") or []:
            if isinstance(item, dict):
                blob_parts.append(str(item.get("label") or ""))
                blob_parts.append(str(item.get("text") or ""))
        enriched.append(row)

    auto_guides = extract_term_guides(*blob_parts, max_items=3)
    if not auto_guides:
        return enriched

    for row in enriched:
        layout = str(row.get("layout_type") or "")
        if layout in {"cta", "template_cta"}:
            existing = list(row.get("term_guides") or [])
            if not existing:
                row["term_guides"] = auto_guides
            break
    else:
        last = dict(enriched[-1])
        if str(last.get("layout_type") or "").endswith("cta") or not last.get("term_guides"):
            merged = list(last.get("term_guides") or [])
            for g in auto_guides:
                if g not in merged:
                    merged.append(g)
            last["term_guides"] = merged[:3]
            enriched[-1] = last

    return enriched
