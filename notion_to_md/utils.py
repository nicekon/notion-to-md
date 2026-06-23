from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


NOTION_ID_RE = re.compile(
    r"(?i)([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}|[0-9a-f]{32})"
)


def hyphenate_notion_id(raw_id: str) -> str:
    compact = raw_id.replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", compact):
        raise ValueError("Notion ID는 32자리 hex 문자열이어야 합니다.")
    return (
        f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
        f"{compact[16:20]}-{compact[20:32]}"
    )


def extract_notion_id(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Notion DB URL 또는 ID를 입력해 주세요.")

    parsed = urlparse(text)
    search_space = parsed.path if parsed.scheme and parsed.netloc else text
    matches = NOTION_ID_RE.findall(search_space)
    if not matches:
        matches = NOTION_ID_RE.findall(text)
    if not matches:
        raise ValueError("입력값에서 Notion database/data source ID를 찾지 못했습니다.")
    return hyphenate_notion_id(matches[0])


def now_stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory
