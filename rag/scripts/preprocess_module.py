import json
import re
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAG_DIR = BASE_DIR.parent
RAW_DIR = RAG_DIR / "raw"
OUTPUT_DIR = RAG_DIR / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_unicode_whitespace(text: str) -> str:
    """NBSP(U+00A0), ZWSP(U+200B) 등 유니코드 공백·제로폭 문자 정리."""
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if ch in "\n\r\t":
            out.append(ch)
            continue
        code = ord(ch)
        cat = unicodedata.category(ch)
        if cat == "Zs" or 0x2000 <= code <= 0x200A or code == 0x00A0:
            out.append(" ")
        elif code in (0x200B, 0x200C, 0x200D, 0xFEFF):
            continue
        else:
            out.append(ch)
    collapsed = "".join(out)
    return re.sub(r" +", " ", collapsed)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = normalize_unicode_whitespace(text)
    text = text.replace("_x000D_", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    return "\n".join(lines).strip()


def safe_get(data, *keys, default=""):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def iter_json_files(root: Path):
    return root.rglob("*.json")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)