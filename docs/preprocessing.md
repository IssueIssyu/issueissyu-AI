# 민원 데이터 전처리 가이드

본 문서는 AI Hub 민원 데이터셋을 RAG 학습용 데이터로 변환하기 위한 전처리 과정과 사용 방법을 설명합니다.

---

## 1. 데이터셋 세팅

AI Hub에서 다운로드한 원본 JSON 파일을 아래 경로에 배치합니다.

```
rag/raw/tl1/
rag/raw/qna/
```

- tl1 : 민원 텍스트 데이터
- qna : 질의응답 데이터

---

## 2. 전처리 실행 방법

아래 명령어를 통해 전처리를 실행합니다.

```bash
cd rag/scripts
python preprocess_tl1.py
python preprocess_qna.py
```

---

## 3. 결과 파일

전처리 결과는 아래 경로에 생성됩니다.

```
rag/output/
```

### 생성 파일 목록

#### TL1 데이터
- tl1_rag_documents.jsonl : RAG 입력용 전체 데이터
- tl1_rag_preview.json : 샘플 데이터
- tl1_preprocessing_report.json : 전처리 통계

#### QnA 데이터
- qna_rag_documents.jsonl
- qna_rag_preview.json
- qna_preprocessing_report.json

---

## 4. 전처리 데이터 구조

각 데이터는 아래 형태로 변환됩니다.

```json
{
  "doc_id": "...",
  "source_file": "...",
  "source_path": "...",
  "publish_date": "...",
  "category": "...",
  "subcategory": "...",
  "predication": "...",
  "department": "...",
  "text": "...",
  "rag_text": "..."
}
```

---

## 5. RAG 입력 텍스트 구성

rag_text는 검색 성능을 높이기 위해 아래 형식으로 구성됩니다.

```
[민원 대분류] ...
[민원 소분류] ...
[민원 유형] ...
[담당 부서] ...
[민원 내용]
...
```

---

## 6. 전처리 로직 요약

- JSON 파일을 순회하며 documents 필드 추출
- 텍스트 정제 (clean_text)
- 메타데이터 추출 (safe_get)
- RAG 입력 텍스트 생성 (build_rag_text)
- JSONL 형태로 저장

---

## 7. 예외 처리

- JSON 파싱 오류 발생 시 해당 파일은 건너뜁니다.
- 전체 전처리는 중단되지 않고 계속 진행됩니다.

---

## 8. 공통 모듈

전처리에서 사용하는 공통 함수는 아래 파일에서 관리됩니다.

```
rag/scripts/preprocess_module.py
```

### 포함 기능

- clean_text : 텍스트 정제
- safe_get : 안전한 데이터 접근
- load_json : JSON 로딩
- iter_json_files : JSON 파일 탐색

---

## 9. 참고

- 전처리 결과(JSONL)는 이후 임베딩 및 벡터 DB(pgvector) 저장에 사용됩니다.
- rag_text 필드는 RAG 검색 및 생성 단계에서 핵심 입력으로 활용됩니다.