from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType

Point2D = tuple[float, float]


class PGPointType(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_kw: Any) -> str:
        return "POINT"

    def bind_processor(self, _dialect: Any):
        def process(value: Any) -> str | None:
            if value is None:
                return None

            if isinstance(value, (tuple, list)) and len(value) == 2:
                return f"({float(value[0])},{float(value[1])})"

            if isinstance(value, dict) and "x" in value and "y" in value:
                return f"({float(value['x'])},{float(value['y'])})"

            raise ValueError("point 값은 (x, y) 튜플/리스트 또는 {'x','y'} dict 이어야 합니다.")

        return process

    def result_processor(self, _dialect: Any, _coltype: Any):
        def process(value: Any) -> Point2D | None:
            if value is None:
                return None

            if hasattr(value, "x") and hasattr(value, "y"):
                return float(value.x), float(value.y)

            if isinstance(value, (tuple, list)) and len(value) == 2:
                return float(value[0]), float(value[1])

            if isinstance(value, str):
                raw = value.strip()
                if raw.startswith("(") and raw.endswith(")"):
                    raw = raw[1:-1]
                x, y = raw.split(",", 1)
                return float(x), float(y)

            raise ValueError(f"point 결과 변환 실패: {value!r}")

        return process
