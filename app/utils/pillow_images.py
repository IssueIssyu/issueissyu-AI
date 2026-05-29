from __future__ import annotations

_heif_opener_registered = False


def ensure_heif_opener() -> None:
    """Pillow에 HEIC/HEIF 디코더를 등록한다. 프로세스당 한 번만 실행."""
    global _heif_opener_registered
    if _heif_opener_registered:
        return
    from pillow_heif import register_heif_opener

    register_heif_opener()
    _heif_opener_registered = True
