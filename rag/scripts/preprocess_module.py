import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAG_DIR = BASE_DIR.parent
RAW_DIR = RAG_DIR / "raw"
OUTPUT_DIR = RAG_DIR / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(text: str) -> str:
    if not text:
        return ""

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