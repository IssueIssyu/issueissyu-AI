from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from starlette import status


class ErrorCode(Enum):

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
    ISSUE_PIN_PROMPT_EMPTY = (
        status.HTTP_400_BAD_REQUEST,
        "ISSUE_4002",
        "핀 생성 프롬프트가 비어 있습니다.",
    )
    ISSUE_PIN_LLM_NO_OUTPUT = (
        status.HTTP_502_BAD_GATEWAY,
        "ISSUE_5021",
        "핀 생성 모델 응답이 비어 있습니다.",
    )
    ISSUE_PIN_LLM_BLOCKED = (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "ISSUE_4222",
        "핀 생성 모델 응답을 가져올 수 없습니다. (차단 또는 형식 오류)",
    )
    ISSUE_PIN_EDIT_VALIDATION = (
        status.HTTP_400_BAD_REQUEST,
        "ISSUE_PIN_EDIT_400_1",
        "필수 요청 값 누락.",
    )
    ISSUE_PIN_EDIT_FAILED = (
        status.HTTP_400_BAD_REQUEST,
        "ISSUE_PIN_EDIT_400_2",
        "이슈 핀 수정 API를 실행 할 수 없습니다.",
    )
    ISSUE_PIN_IMPORT_VALIDATION = (
        status.HTTP_400_BAD_REQUEST,
        "ISSUE_PIN_IMPORT_400_1",
        "필수 요청 값 누락.",
    )
    ISSUE_PIN_IMPORT_FAILED = (
        status.HTTP_400_BAD_REQUEST,
        "ISSUE_PIN_IMPORT_400_2",
        "이슈 핀 등록 API를 실행 할 수 없습니다.",
    )
    PIN_IMAGE_TOTAL_SIZE_EXCEEDED = (
        status.HTTP_400_BAD_REQUEST,
        "PIN_IMAGE_400_1",
        "첨부한 사진 용량이 너무 큽니다.",
    )
    PIN_IMAGE_UPLOAD_FAILED = (
        status.HTTP_400_BAD_REQUEST,
        "PIN_IMAGE_400_2",
        "사진 첨부에 실패했습니다.",
    )
    PIN_IMAGE_COUNT_EXCEEDED = (
        status.HTTP_400_BAD_REQUEST,
        "PIN_IMAGE_400_3",
        "최대 사진 첨부 갯수를 초과했습니다.",
    )

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

    # Issue
    ISSUE_PIN_GET_SUCCESS = (
        status.HTTP_200_OK,
        "ISSUE_2001",
        "이슈 핀 상세 조회에 성공했습니다.",
    )
    ISSUE_PIN_RELIABILITY_GET_SUCCESS = (
        status.HTTP_200_OK,
        "ISSUE_2002",
        "이슈 핀 신뢰도 조회에 성공했습니다.",
    )
    ISSUE_PIN_EDIT_SUCCESS = (
        status.HTTP_200_OK,
        "ISSUE_PIN_EDIT_200",
        "이슈 핀 수정에 성공했습니다.",
    )
    ISSUE_PIN_IMPORT_SUCCESS = (
        status.HTTP_201_CREATED,
        "ISSUE_PIN_IMPORT_201",
        "이슈 핀 등록에 성공했습니다.",
    )

    COMPLAINT_EMAIL_GENERATE_SUCCESS = (
        status.HTTP_201_CREATED,
        "COMPLAINT_201",
        "청원 이메일 패키지 생성에 성공했습니다.",
    )
    COMPLAINT_APPLY_SUCCESS = (
        status.HTTP_201_CREATED,
        "COMPLAINT_202",
        "민원 신청 자동 생성에 성공했습니다.",
    )
    COMPLAINT_BOOTSTRAP_SUCCESS = (
        status.HTTP_200_OK,
        "COMPLAINT_2001",
        "민원 부서/지역 매핑 시드에 성공했습니다.",
    )
    COMPLAINT_BULK_SEND_SUCCESS = (
        status.HTTP_200_OK,
        "COMPLAINT_2002",
        "민원 일괄 송신 처리에 성공했습니다.",
    )
    COMPLAINT_SCHEDULER_RUN_SUCCESS = (
        status.HTTP_200_OK,
        "COMPLAINT_2003",
        "민원 자동 생성 스케줄러 테스트 실행에 성공했습니다.",
    )
    FESTIVAL_FETCH_SUCCESS = (
        status.HTTP_200_OK,
        "FESTIVAL_2001",
        "축제 데이터 수집에 성공했습니다.",
    )
    FESTIVAL_TRANSFORM_BATCH_SUCCESS = (
        status.HTTP_201_CREATED,
        "FESTIVAL_2011",
        "축제 LLM 배치 가공에 성공했습니다.",
    )
    FESTIVAL_IMPORT_BATCH_SUCCESS = (
        status.HTTP_201_CREATED,
        "FESTIVAL_2012",
        "축제 DB 배치 적재에 성공했습니다.",
    )
    FESTIVAL_IMPORT_ALL_SUCCESS = (
        status.HTTP_201_CREATED,
        "FESTIVAL_2013",
        "축제 DB 일괄 적재에 성공했습니다.",
    )
    FESTIVAL_STATUS_SUCCESS = (
        status.HTTP_200_OK,
        "FESTIVAL_2002",
        "축제 파이프라인 상태 조회에 성공했습니다.",
    )
    FESTIVAL_HANDOFF_SUCCESS = (
        status.HTTP_200_OK,
        "FESTIVAL_2003",
        "축제 핸드오프 조회에 성공했습니다.",
    )
    FESTIVAL_RESET_SUCCESS = (
        status.HTTP_200_OK,
        "FESTIVAL_2004",
        "축제 파이프라인 로컬 캐시 초기화에 성공했습니다.",
    )
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
