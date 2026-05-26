from __future__ import annotations


def format_notification_email_subject(*, pin_title: str, department: str | None = None) -> str:
    title = pin_title.strip() or "민원 의견서"
    department_line = department.strip() if isinstance(department, str) and department.strip() else "담당부서"
    return f"[민원 자동 생성] {title} ({department_line})"


def format_notification_email_body(
    *,
    pin_title: str,
    pin_content: str,
    opinion_summary: str,
    reliability_score: float,
    validity: bool,
    risk_note: str | None,
    department: str | None = None,
) -> str:
    title = pin_title.strip()
    content = pin_content.strip()
    summary = opinion_summary.strip() or f"{title}\n{content}".strip()
    risk_line = risk_note.strip() if risk_note and risk_note.strip() else "없음"
    department_line = department.strip() if isinstance(department, str) and department.strip() else "미지정"
    validity_ko = "유효" if validity else "추가 확인 필요"
    score_pct = round(max(0.0, min(1.0, reliability_score)) * 100, 1)

    return (
        f"안녕하세요.\n\n"
        f"이슈 핀 「{title}」에 대한 청원 의견서 초안(PDF)을 첨부하여 보내드립니다.\n\n"
        f"【민원 요약】\n{summary}\n\n"
        f"【자동 검증 참고】 신뢰도 {score_pct}% ({validity_ko}). "
        f"참고 사항: {risk_line}\n"
        f"【추천 담당 부서】 {department_line}\n"
        f"위 점수는 AI 추정치이며, 최종 판단 및 조치는 담당 부서에서 결정됩니다.\n\n"
        f"첨부 PDF를 확인해 주시고, 문의 사항이 있으시면 회신 부탁드립니다.\n"
        f"감사합니다."
    )
