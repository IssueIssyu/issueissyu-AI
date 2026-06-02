from __future__ import annotations

# TourAPI KorService2 시·도 areaCode (공공데이터포털 한국관광공사 코드표)
TOURAPI_AREA_NAMES: dict[str, str] = {
    "1": "서울",
    "2": "인천",
    "3": "대전",
    "4": "대구",
    "5": "광주",
    "6": "부산",
    "7": "울산",
    "8": "세종",
    "31": "경기",
    "32": "강원",
    "33": "충북",
    "34": "충남",
    "35": "경북",
    "36": "경남",
    "37": "전북",
    "38": "전남",
    "39": "제주",
}

VALID_AREA_CODES = frozenset(TOURAPI_AREA_NAMES)

# TourAPI list/detail 응답 areacode가 비어 있는 경우가 많아 addr1 접두사로 추론
_ADDR_AREA_PREFIXES: tuple[tuple[str, str], ...] = (
    ("서울특별시", "1"),
    ("서울", "1"),
    ("인천광역시", "2"),
    ("인천", "2"),
    ("대전광역시", "3"),
    ("대전", "3"),
    ("대구광역시", "4"),
    ("대구", "4"),
    ("광주광역시", "5"),
    ("광주", "5"),
    ("부산광역시", "6"),
    ("부산", "6"),
    ("울산광역시", "7"),
    ("울산", "7"),
    ("세종특별자치시", "8"),
    ("세종", "8"),
    ("경기도", "31"),
    ("경기", "31"),
    ("강원특별자치도", "32"),
    ("강원도", "32"),
    ("강원", "32"),
    ("충청북도", "33"),
    ("충북", "33"),
    ("충청남도", "34"),
    ("충남", "34"),
    ("경상북도", "35"),
    ("경북", "35"),
    ("경상남도", "36"),
    ("경남", "36"),
    ("전북특별자치도", "37"),
    ("전라북도", "37"),
    ("전북", "37"),
    ("전라남도", "38"),
    ("전남", "38"),
    ("제주특별자치도", "39"),
    ("제주도", "39"),
    ("제주", "39"),
)


def infer_area_code_from_addr(addr: str | None) -> str | None:
    text = (addr or "").strip()
    if not text:
        return None
    for prefix, code in _ADDR_AREA_PREFIXES:
        if text.startswith(prefix):
            return code
    return None


def resolve_row_area_code(row: dict) -> str | None:
    explicit = str(row.get("area_code") or row.get("areacode") or "").strip()
    if explicit:
        return explicit
    addr = str(row.get("addr") or row.get("addr1") or "").strip()
    return infer_area_code_from_addr(addr)


def area_display_name(area_code: str | None) -> str | None:
    if area_code is None:
        return None
    return TOURAPI_AREA_NAMES.get(area_code.strip())


def validate_area_code(value: str | None, *, label: str = "area_code") -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text not in VALID_AREA_CODES:
        known = ", ".join(
            f"{code}({name})"
            for code, name in sorted(TOURAPI_AREA_NAMES.items(), key=lambda x: int(x[0]))
        )
        raise ValueError(f"{label}는 TourAPI 시·도 코드여야 합니다 (받음: {value!r}). 허용: {known}")
    return text


def validate_sigungu_code(
    value: str | None,
    *,
    area_code: str | None,
    label: str = "sigungu_code",
) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if area_code is None:
        raise ValueError(f"{label}는 area_code와 함께 지정해야 합니다.")
    if not text.isdigit():
        raise ValueError(f"{label}는 숫자 코드여야 합니다 (받음: {value!r})")
    return text


def row_matches_area_filter(
    row: dict,
    *,
    area_code: str | None,
    sigungu_code: str | None,
) -> bool:
    if area_code is None:
        return True
    row_area = resolve_row_area_code(row)
    if row_area != area_code:
        return False
    if sigungu_code is None:
        return True
    row_sigungu = str(row.get("sigungu_code") or row.get("sigungucode") or "").strip()
    return row_sigungu == sigungu_code
