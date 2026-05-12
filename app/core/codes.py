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

    # VLM (Gemini)
    VLM_NOT_CONFIGURED = (status.HTTP_503_SERVICE_UNAVAILABLE, "VLM_5031", "VLM(Gemini) API 키가 설정되지 않았습니다.")

    # Issue
    ISSUE_LOW_RELIABILITY = (status.HTTP_422_UNPROCESSABLE_ENTITY, "ISSUE_4221", "신뢰도가 낮아 이슈 핀을 생성할 수 없습니다.")
    ISSUE_NOT_FOUND = (status.HTTP_404_NOT_FOUND, "ISSUE_4041", "존재하지 않는 이슈 핀입니다.")

    # VLM (Gemini)
    VLM_NOT_CONFIGURED = (status.HTTP_503_SERVICE_UNAVAILABLE, "VLM_5031", "VLM(Gemini) API 키가 설정되지 않았습니다.")

    # File / Upload
    FILE_NOT_FOUND = (status.HTTP_404_NOT_FOUND, "FILE_4041", "파일을 찾을 수 없습니다.")
    FILE_UPLOAD_ERROR = (status.HTTP_400_BAD_REQUEST, "FILE_4001", "파일 업로드 중 오류가 발생했습니다.")
    FILE_TYPE_NOT_SUPPORTED = (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "FILE_4151", "지원하지 않는 파일 형식입니다.")
    FILE_SIZE_TOO_LARGE = (status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "FILE_4131", "파일 크기가 너무 큽니다.")

    @property
    def http_status(self) -> int:
        return int(self.value[0])

    @property
    def code(self) -> str:
        return str(self.value[1])

    @property
    def message(self) -> str:
        return str(self.value[2])


class SuccessCode(Enum):
    """성공 코드 정의 (HTTP 상태, 문자열 코드, 기본 메시지)"""

    # Common
    OK = (status.HTTP_200_OK, "COMMON_200", "Success")
    CREATED = (status.HTTP_201_CREATED, "COMMON_201", "Created")

    # User
    USER_LOGIN_SUCCESS = (status.HTTP_201_CREATED, "USER_2011", "회원가입& 로그인이 완료되었습니다.")
    USER_LOGOUT_SUCCESS = (status.HTTP_200_OK, "USER_2001", "로그아웃 되었습니다.")
    USER_REISSUE_SUCCESS = (status.HTTP_200_OK, "USER_2002", "토큰 재발급이 완료되었습니다.")
    USER_DELETE_SUCCESS = (status.HTTP_200_OK, "USER_2003", "회원탈퇴가 완료되었습니다.")
    USER_PROFILE_UPDATE_SUCCESS = (status.HTTP_200_OK, "USER_2006", "프로필 저장이 완료되었습니다.")
    USER_INFO_GET_SUCCESS = (status.HTTP_200_OK, "USER_2007", "유저 정보 조회가 완료되었습니다.")

    @property
    def http_status(self) -> int:
        return int(self.value[0])

    @property
    def code(self) -> str:
        return str(self.value[1])

    @property
    def message(self) -> str:
        return str(self.value[2])

    def get_reason(self) -> dict[str, int | str]:
        return {
            "httpStatus": self.http_status,
            "code": self.code,
            "message": self.message,
        }
