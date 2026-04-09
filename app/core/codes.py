from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from starlette import status


class ErrorCode(Enum):
    """에러 코드 정의 (HTTP 상태, 문자열 코드, 기본 메시지)"""

    # Common
    BAD_REQUEST = (status.HTTP_400_BAD_REQUEST, "COMMON_400", "잘못된 요청입니다.")
    UNAUTHORIZED = (status.HTTP_401_UNAUTHORIZED, "COMMON_401", "인증이 필요합니다.")
    FORBIDDEN = (status.HTTP_403_FORBIDDEN, "COMMON_403", "접근 권한이 없습니다.")
    NOT_FOUND = (status.HTTP_404_NOT_FOUND, "COMMON_404", "요청한 리소스를 찾을 수 없습니다.")
    VALIDATION_ERROR = (status.HTTP_422_UNPROCESSABLE_ENTITY, "COMMON_422", "입력 데이터가 올바르지 않습니다.")
    INTERNAL_SERVER_ERROR = (status.HTTP_500_INTERNAL_SERVER_ERROR, "COMMON_500", "서버 에러")

    # User
    USER_NOT_FOUND = (status.HTTP_404_NOT_FOUND, "USER_4041", "존재하지 않는 회원입니다.")
    USER_NOT_FOUND_BY_EMAIL = (status.HTTP_404_NOT_FOUND, "USER_4042", "EMAIL이 존재하지 않는 회원입니다.")
    USER_NOT_FOUND_BY_USERNAME = (status.HTTP_404_NOT_FOUND, "USER_4043", "USERNAME이 존재하지 않는 회원입니다.")
    USER_ALREADY_EXISTS = (status.HTTP_409_CONFLICT, "USER_4091", "이미 존재하는 사용자입니다.")
    USER_EMAIL_EXISTS = (status.HTTP_409_CONFLICT, "USER_4092", "이미 사용 중인 이메일입니다.")
    USER_INVALID_CREDENTIALS = (status.HTTP_401_UNAUTHORIZED, "USER_4011", "잘못된 인증 정보입니다.")

    # Login / JWT
    TOKEN_INVALID = (status.HTTP_403_FORBIDDEN, "JWT_4032", "유효하지 않은 token입니다.")
    TOKEN_NO_AUTH = (status.HTTP_403_FORBIDDEN, "JWT_4033", "권한 정보가 없는 token입니다.")
    TOKEN_EXPIRED = (status.HTTP_401_UNAUTHORIZED, "JWT_4011", "token 유효기간이 만료되었습니다.")

    # File / Upload
    FILE_NOT_FOUND = (status.HTTP_404_NOT_FOUND, "FILE_4041", "파일을 찾을 수 없습니다.")
    FILE_UPLOAD_ERROR = (status.HTTP_400_BAD_REQUEST, "FILE_4001", "파일 업로드 중 오류가 발생했습니다.")
    FILE_TYPE_NOT_SUPPORTED = (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "FILE_4151", "지원하지 않는 파일 형식입니다.")
    FILE_SIZE_TOO_LARGE = (status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "FILE_4131", "파일 크기가 너무 큽니다.")

    # Infra / External
    DATABASE_ERROR = (status.HTTP_500_INTERNAL_SERVER_ERROR, "DB_5001", "데이터베이스 오류가 발생했습니다.")
    TRANSACTION_ERROR = (status.HTTP_500_INTERNAL_SERVER_ERROR, "DB_5002", "트랜잭션 처리 중 오류가 발생했습니다.")
    S3_UPLOAD_ERROR = (status.HTTP_503_SERVICE_UNAVAILABLE, "S3_5031", "파일 저장에 실패했습니다.")
    PDF_PROCESSING_ERROR = (status.HTTP_500_INTERNAL_SERVER_ERROR, "PDF_5001", "PDF 처리 중 오류가 발생했습니다.")
    AI_PROCESSING_ERROR = (status.HTTP_500_INTERNAL_SERVER_ERROR, "AI_5001", "AI 분석 처리 중 오류가 발생했습니다.")
    AI_REPORT_NOT_FOUND = (status.HTTP_404_NOT_FOUND, "AI_4041", "AI REPORT를 찾을 수 없습니다.")
    AI_REPORT_NOT_VALID_GRADE_TERM = (status.HTTP_400_BAD_REQUEST, "AI_4001", "부적절한 학년 학기 요청")

    @property
    def http_status(self) -> int:
        return int(self.value[0])

    @property
    def code(self) -> str:
        return str(self.value[1])

    @property
    def message(self) -> str:
        return str(self.value[2])
