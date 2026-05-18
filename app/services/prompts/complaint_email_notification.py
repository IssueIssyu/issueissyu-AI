from __future__ import annotations


def complaint_notification_prompt(
    *,
    pin_title: str,
    pin_content: str,
    opinion_summary: str,
    reliability_score: float,
    validity: bool,
    risk_note: str | None,
) -> str:
    risk_line = risk_note.strip() if risk_note and risk_note.strip() else "없음"
    validity_ko = "유효" if validity else "추가 확인 필요"
    score_pct = round(reliability_score * 100, 1)
    pin_fallback = f"{pin_title.strip()}\n{pin_content.strip()}".strip()
    return f"""
        [역할]
        청원 의견서 PDF를 메일로 보낼 때 함께 실을 본문(plain text)을 작성한다.
        
        [이슈 핀]
        제목: {pin_title.strip()}
        본문: {pin_content.strip()}
        
        [민원 요약]
        {opinion_summary.strip() or pin_fallback}
        
        [신뢰도]
        - 점수: {score_pct}% (0~100, 모델 추정)
        - 판정: {validity_ko}
        - 참고: {risk_line}
        
        [작성 규칙]
        - 3~6문장, 정중한 안내 톤.
        - PDF 첨부 안내, 신뢰도 점수는 참고용이며 최종 판단은 담당 부서임을 한 문장 포함.
        - HTML·마크다운 없이 본문 텍스트만 출력.
    """.strip()
