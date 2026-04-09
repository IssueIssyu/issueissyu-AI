from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.core.codes import ErrorCode

class CustomException(Exception):
    """커스텀 예외 베이스"""

    def __init__(self, error_code: ErrorCode, detail: Optional[str] = None, **kwargs: Any):
        self.error_code = error_code
        self.detail = detail or error_code.message
        self.extra = kwargs
        super().__init__(self.detail)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.error_code.code,
            "message": self.detail,
            **self.extra,
        }


class BusinessException(CustomException):
    """비즈니스 로직 예외"""

    pass


class ValidationException(CustomException):
    """검증 예외"""

    pass


class DatabaseException(CustomException):
    """데이터베이스 예외"""

    pass


class FileException(CustomException):
    """파일 처리 예외"""

    pass




def create_http_exception(exception: CustomException) -> HTTPException:
    status_code = exception.error_code.http_status
    return HTTPException(status_code=status_code, detail=exception.to_dict())


def raise_business_exception(error_code: ErrorCode, detail: Optional[str] = None, **kwargs: Any) -> None:
    raise BusinessException(error_code, detail, **kwargs)


def raise_validation_exception(error_code: ErrorCode, detail: Optional[str] = None, **kwargs: Any) -> None:
    raise ValidationException(error_code, detail, **kwargs)


def raise_database_exception(error_code: ErrorCode, detail: Optional[str] = None, **kwargs: Any) -> None:
    raise DatabaseException(error_code, detail, **kwargs)


def raise_file_exception(error_code: ErrorCode, detail: Optional[str] = None, **kwargs: Any) -> None:
    raise FileException(error_code, detail, **kwargs)
