from __future__ import annotations

from pathlib import Path


def resolve_package_relative_path(package_dir: Path, raw: str) -> Path:
    """패키지 디렉터리 기준 상대 경로를 해석한다. 절대 경로면 그대로 반환."""
    path = Path(raw)
    if path.is_absolute():
        return path
    return (package_dir / path).resolve()


_POLICY_CARDNEWS_DIR = Path(__file__).resolve().parent
_CONTEST_CARDNEWS_DIR = _POLICY_CARDNEWS_DIR.parent / "contest_cardnews"


def cardnews_font_dir(*, package_dir: Path | None = None) -> Path:
    from app.core.config import settings

    base = package_dir or _POLICY_CARDNEWS_DIR
    return resolve_package_relative_path(base, settings.policy_cardnews_font_dir)


def contest_cardnews_font_dir() -> Path:
    return cardnews_font_dir(package_dir=_CONTEST_CARDNEWS_DIR)


def cardnews_mascot_dir() -> Path:
    from app.core.config import settings

    configured = (settings.policy_cardnews_mascot_dir or "").strip()
    if not configured:
        return resolve_package_relative_path(_POLICY_CARDNEWS_DIR, "../assets/mascots")
    return resolve_package_relative_path(_POLICY_CARDNEWS_DIR, configured)
