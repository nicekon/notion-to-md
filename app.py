from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from notion_to_md.exporter import (
    build_export_filename,
    create_zip_bytes,
    page_title,
    property_to_text,
    write_export_summary_file,
    write_markdown_file,
)
from notion_to_md.filters import (
    build_api_filter,
    comma_terms,
    keyword_matches,
    option_values,
    person_filter_matches,
    property_schema_by_type,
)
from notion_to_md.notion_client import NotionAPIError, NotionClient
from notion_to_md.utils import extract_notion_id, now_stamp


load_dotenv()


st.set_page_config(page_title="Notion to Markdown", page_icon="N", layout="wide")


PRESETS_PATH = Path("presets.json")
APP_VERSION = "v2026.06.24-comments-only"


def render_app_footer() -> None:
    st.caption(f"Notion to Markdown · {APP_VERSION}")


def get_client(token: str, notion_version: str) -> NotionClient:
    return NotionClient(token=token, notion_version=notion_version)


def schema_options(properties: dict[str, dict], prop_types: set[str], label: str) -> list[str]:
    values = property_schema_by_type(properties, prop_types)
    return ["사용 안 함"] + values if values else ["사용 안 함"]


def selected_or_none(value: str) -> str | None:
    return None if value == "사용 안 함" else value


PROPERTY_RECOMMENDATIONS = {
    "date": {
        "type_bonus": {"date": 30, "created_time": 18, "last_edited_time": 12},
        "keywords": [
            ("날짜", 30),
            ("일자", 30),
            ("기간", 26),
            ("date", 26),
            ("작성일", 24),
            ("생성일", 22),
            ("created", 18),
            ("발행", 18),
            ("published", 18),
            ("마감", 16),
            ("due", 16),
            ("수정", 10),
            ("edited", 10),
            ("updated", 10),
        ],
    },
    "person": {
        "type_bonus": {"people": 30, "created_by": 14, "last_edited_by": 8},
        "keywords": [
            ("담당자", 34),
            ("담당", 30),
            ("assignee", 30),
            ("owner", 26),
            ("pic", 24),
            ("responsible", 22),
            ("작성자", 18),
            ("creator", 14),
            ("created", 10),
            ("수정자", 8),
            ("editor", 8),
        ],
    },
    "option": {
        "type_bonus": {"status": 34, "select": 20, "multi_select": 14},
        "keywords": [
            ("상태", 34),
            ("status", 34),
            ("진행", 28),
            ("단계", 24),
            ("stage", 24),
            ("phase", 22),
            ("state", 20),
            ("분류", 16),
            ("category", 16),
            ("유형", 14),
            ("type", 14),
            ("태그", 10),
            ("tag", 10),
        ],
    },
}

FILENAME_STYLE_OPTIONS = {
    "제목-페이지ID.md": "title_id",
    "제목.md": "title",
    "날짜_제목.md": "date_title",
    "상태_제목.md": "option_title",
    "담당자_제목.md": "person_title",
    "날짜_상태_제목.md": "date_option_title",
}

DATE_FILTER_MODES = ["전체", "시작일 이후", "종료일 이전", "기간"]
WIZARD_STEPS = {
    1: "연결",
    2: "검색",
    3: "내보내기",
}


def set_wizard_step(step: int) -> None:
    st.session_state["wizard_step"] = max(1, min(step, len(WIZARD_STEPS)))


def render_wizard_header(step: int) -> None:
    labels = []
    for number, label in WIZARD_STEPS.items():
        text = f"{number}. {label}"
        labels.append(f"**{text}**" if number == step else text)
    st.caption(" > ".join(labels))
    st.progress((step - 1) / (len(WIZARD_STEPS) - 1))
    st.subheader(f"{step}. {WIZARD_STEPS[step]}")


def render_wizard_nav(
    *,
    current_step: int,
    previous_step: int | None = None,
    next_step: int | None = None,
    next_label: str = "다음",
    next_disabled: bool = False,
) -> None:
    st.divider()
    previous_col, spacer_col, next_col = st.columns([1, 3, 1])
    if previous_step is not None:
        if previous_col.button("이전", key=f"wizard_previous_{current_step}", width="stretch"):
            set_wizard_step(previous_step)
            st.rerun()
    if next_step is not None:
        if next_col.button(
            next_label,
            key=f"wizard_next_{current_step}",
            type="primary",
            disabled=next_disabled,
            width="stretch",
        ):
            set_wizard_step(next_step)
            st.rerun()


def load_presets() -> dict[str, dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return {}
    try:
        payload = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_presets(presets: dict[str, dict[str, Any]]) -> None:
    PRESETS_PATH.write_text(
        json.dumps(presets, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_schema_into_state(
    token: str,
    notion_version: str,
    db_url: str,
    *,
    preferred_data_source_id: str | None = None,
) -> None:
    database_id = extract_notion_id(db_url)
    client = get_client(token, notion_version)
    data_sources = client.list_data_sources(database_id)
    if not data_sources:
        raise NotionAPIError("이 DB에서 data source를 찾지 못했습니다.")
    available_ids = {item.id for item in data_sources}
    selected_id = preferred_data_source_id if preferred_data_source_id in available_ids else data_sources[0].id

    st.session_state["database_id"] = database_id
    st.session_state["data_sources"] = [item.__dict__ for item in data_sources]
    st.session_state["selected_data_source_id"] = selected_id
    st.session_state["data_source_schema"] = client.retrieve_data_source(selected_id).get("properties", {})


def parse_preset_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def date_to_preset_value(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return None


def apply_preset_to_state(name: str, preset: dict[str, Any], token: str) -> None:
    clear_preview(reset_property_selection=True)

    simple_keys = [
        "db_url",
        "notion_version",
        "export_dir",
        "date_property",
        "person_property",
        "option_property",
        "option_value",
        "date_filter_mode",
        "include_body_preview",
        "person_terms",
        "keyword",
        "max_pages",
        "filename_style_label",
        "include_frontmatter",
        "include_properties",
        "include_comments_section",
        "omit_empty_comments",
        "only_pages_with_comments",
        "comments_only_export",
        "include_source_url",
        "comment_scope",
        "max_comment_blocks",
    ]
    for key in simple_keys:
        if key in preset and preset[key] is not None:
            st.session_state[key] = preset[key]

    st.session_state["start_date"] = parse_preset_date(preset.get("start_date"))
    st.session_state["end_date"] = parse_preset_date(preset.get("end_date"))

    db_url = preset.get("db_url") or ""
    notion_version = preset.get("notion_version") or os.getenv("NOTION_VERSION", "2025-09-03")
    if token and db_url:
        try:
            load_schema_into_state(
                token,
                notion_version,
                db_url,
                preferred_data_source_id=preset.get("selected_data_source_id"),
            )
            st.session_state["preset_notice"] = ("success", f"`{name}` 프리셋을 불러왔습니다.")
        except (ValueError, NotionAPIError) as exc:
            st.session_state["preset_notice"] = (
                "warning",
                f"`{name}` 프리셋 값은 적용했지만 스키마 로드는 실패했습니다: {exc}",
            )
    else:
        st.session_state["preset_notice"] = ("info", f"`{name}` 프리셋 값을 적용했습니다. 토큰과 DB URL을 확인해 주세요.")


def current_preset_payload(
    *,
    db_url: str,
    notion_version: str,
    export_dir: str,
    selected_data_source_id: str | None,
) -> dict[str, Any]:
    return {
        "db_url": db_url,
        "notion_version": notion_version,
        "export_dir": export_dir,
        "selected_data_source_id": selected_data_source_id,
        "date_property": st.session_state.get("date_property"),
        "date_filter_mode": st.session_state.get("date_filter_mode", "전체"),
        "include_body_preview": st.session_state.get("include_body_preview", False),
        "person_property": st.session_state.get("person_property"),
        "option_property": st.session_state.get("option_property"),
        "option_value": st.session_state.get("option_value"),
        "person_terms": st.session_state.get("person_terms", ""),
        "keyword": st.session_state.get("keyword", ""),
        "start_date": date_to_preset_value(st.session_state.get("start_date")),
        "end_date": date_to_preset_value(st.session_state.get("end_date")),
        "max_pages": st.session_state.get("max_pages", 100),
        "filename_style_label": st.session_state.get("filename_style_label", "제목-페이지ID.md"),
        "include_frontmatter": st.session_state.get("include_frontmatter", True),
        "include_properties": st.session_state.get("include_properties", True),
        "include_comments_section": st.session_state.get("include_comments_section", True),
        "omit_empty_comments": st.session_state.get("omit_empty_comments", True),
        "only_pages_with_comments": st.session_state.get("only_pages_with_comments", False),
        "comments_only_export": st.session_state.get("comments_only_export", False),
        "include_source_url": st.session_state.get("include_source_url", False),
        "comment_scope": st.session_state.get("comment_scope", "페이지 댓글만"),
        "max_comment_blocks": st.session_state.get("max_comment_blocks", 300),
    }


def normalize_property_name(name: str) -> str:
    return name.casefold().replace("_", " ").replace("-", " ").strip()


def recommendation_score(name: str, schema: dict[str, Any], kind: str) -> int:
    rule = PROPERTY_RECOMMENDATIONS[kind]
    prop_type = schema.get("type", "")
    score = rule["type_bonus"].get(prop_type, 0)
    normalized = normalize_property_name(name)
    for keyword, points in rule["keywords"]:
        if keyword in normalized:
            score += points
    return score


def recommended_property_name(properties: dict[str, Any], prop_types: set[str], kind: str) -> str | None:
    candidates = property_schema_by_type(properties, prop_types)
    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda name: (
            recommendation_score(name, properties[name], kind),
            -candidates.index(name),
        ),
        reverse=True,
    )
    return ranked[0]


def select_property(
    label: str,
    properties: dict[str, Any],
    prop_types: set[str],
    kind: str,
    key: str,
) -> str | None:
    options = schema_options(properties, prop_types, label)
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state.pop(key, None)
    recommended = recommended_property_name(properties, prop_types, kind)
    index = options.index(recommended) if recommended in options else 0
    if key in st.session_state:
        selected = st.selectbox(label, options, key=key)
    else:
        selected = st.selectbox(label, options, index=index, key=key)
    return selected_or_none(selected)


def optional_date_input(label: str, key: str, *, default: date | None = None) -> date | None:
    if key in st.session_state and st.session_state[key] is not None:
        return st.date_input(label, key=key)
    st.session_state.pop(key, None)
    return st.date_input(label, value=default, key=key)


def number_input_with_state(
    label: str,
    *,
    key: str,
    default: int,
    min_value: int,
    max_value: int,
    step: int,
    disabled: bool = False,
) -> int:
    if key in st.session_state:
        return st.number_input(label, min_value=min_value, max_value=max_value, step=step, key=key, disabled=disabled)
    return st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        value=default,
        step=step,
        key=key,
        disabled=disabled,
    )


def selectbox_with_state(label: str, options: list[str], *, key: str, default_index: int = 0) -> str:
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state.pop(key, None)
    if key in st.session_state:
        return st.selectbox(label, options, key=key)
    return st.selectbox(label, options, index=default_index, key=key)


def active_date_bounds(date_filter_mode: str, start_date: date | None, end_date: date | None) -> tuple[date | None, date | None]:
    if date_filter_mode == "시작일 이후":
        return start_date, None
    if date_filter_mode == "종료일 이전":
        return None, end_date
    if date_filter_mode == "기간":
        return start_date, end_date or start_date
    return None, None


def validate_date_filter(date_filter_mode: str, date_property: str | None, start_date: date | None, end_date: date | None) -> str | None:
    if date_filter_mode == "전체":
        return None
    if not date_property:
        return "날짜 필터를 쓰려면 기간 기준 속성을 선택해야 합니다."
    if date_filter_mode in {"시작일 이후", "기간"} and not start_date:
        return "시작일을 입력해 주세요."
    if date_filter_mode == "종료일 이전" and not end_date:
        return "종료일을 입력해 주세요."
    if date_filter_mode == "기간" and not end_date:
        end_date = start_date
    if start_date and end_date and start_date > end_date:
        return "시작일은 종료일보다 늦을 수 없습니다."
    return None


def clear_preview(*, reset_property_selection: bool = False) -> None:
    keys = [
        "preview_pages",
        "preview_rows",
        "preview_warnings",
        "preview_skipped",
        "preview_total",
        "preview_config",
        "preview_issues",
        "page_body_cache",
        "export_results",
        "export_files",
        "export_output_dir",
        "export_warnings",
        "export_issues",
        "export_summary_path",
        "export_skipped_no_comments",
        "export_skipped_comment_lookup_failed",
        "preview_editor",
        "preview_editor_with_filename",
    ]
    if reset_property_selection:
        keys.extend(["date_property", "person_property", "option_property"])

    for key in keys:
        st.session_state.pop(key, None)


def fetch_body_markdown(client: NotionClient, page_id: str) -> tuple[str, list[str]]:
    markdown_payload = client.retrieve_page_markdown(page_id)
    body = markdown_payload.get("markdown", "")
    warnings: list[str] = []

    if markdown_payload.get("truncated"):
        warnings.append("본문 Markdown 응답이 Notion API에서 truncated 상태로 내려왔습니다.")
    unknown_blocks = markdown_payload.get("unknown_block_ids") or []
    if unknown_blocks:
        warnings.append(f"알 수 없는 블록 {len(unknown_blocks)}개가 Markdown 변환에서 제외되었습니다.")
    return body, warnings


def exception_message(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def issue_record(page: dict[str, Any], step: str, exc: Exception | str, severity: str = "error") -> dict[str, str]:
    return {
        "severity": severity,
        "step": step,
        "title": page_title(page),
        "message": exception_message(exc) if isinstance(exc, Exception) else exc,
        "url": page.get("url", ""),
        "page_id": page.get("id", ""),
    }


def warning_records(page: dict[str, Any], step: str, warnings: list[str]) -> list[dict[str, str]]:
    return [issue_record(page, step, warning, "warning") for warning in warnings]


def get_cached_body(client: NotionClient, page_id: str) -> tuple[str, list[str]]:
    body_cache = st.session_state.setdefault("page_body_cache", {})
    if page_id in body_cache:
        return body_cache[page_id], []

    body_markdown, warnings = fetch_body_markdown(client, page_id)
    body_cache[page_id] = body_markdown
    return body_markdown, warnings


def page_property_value(page: dict[str, Any], property_name: str | None) -> str:
    if not property_name:
        return ""
    value = page.get("properties", {}).get(property_name)
    return property_to_text(value) if value else ""


def body_preview_text(body_markdown: str, *, max_length: int = 240) -> str:
    text = re.sub(r"```.*?```", " ", body_markdown, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_\-|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def preview_row(
    page: dict[str, Any],
    *,
    date_property: str | None,
    person_property: str | None,
    option_property: str | None,
    body_preview: str = "",
) -> dict[str, Any]:
    return {
        "export": True,
        "title": page_title(page),
        "body_preview": body_preview,
        "date": page_property_value(page, date_property),
        "assignee": page_property_value(page, person_property),
        "status": page_property_value(page, option_property),
        "last_edited": page.get("last_edited_time", ""),
        "url": page.get("url", ""),
        "page_id": page.get("id", ""),
    }


def table_records(rows: Any) -> list[dict[str, Any]]:
    if hasattr(rows, "to_dict"):
        return rows.to_dict("records")
    return list(rows)


def selected_preview_page_ids(rows: Any) -> set[str]:
    return {row["page_id"] for row in table_records(rows) if row.get("export") and row.get("page_id")}


def append_suffix_to_filename(filename: str, suffix_index: int) -> str:
    path = Path(filename)
    return f"{path.stem}-{suffix_index}{path.suffix}"


def preview_rows_with_filenames(
    rows: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    *,
    filename_style: str,
    date_property: str | None,
    person_property: str | None,
    option_property: str | None,
) -> list[dict[str, Any]]:
    pages_by_id = {page.get("id"): page for page in pages}
    filename_counts: dict[str, int] = {}
    rendered_rows: list[dict[str, Any]] = []

    for row in rows:
        rendered_row = dict(row)
        page = pages_by_id.get(row.get("page_id"))
        if not page:
            rendered_row["expected_filename"] = ""
            rendered_rows.append(rendered_row)
            continue

        filename = build_export_filename(
            page,
            filename_style=filename_style,
            date_property=date_property,
            person_property=person_property,
            option_property=option_property,
        )
        filename_counts[filename] = filename_counts.get(filename, 0) + 1
        if filename_counts[filename] > 1:
            filename = append_suffix_to_filename(filename, filename_counts[filename])
        rendered_row["expected_filename"] = filename
        rendered_rows.append(rendered_row)

    return rendered_rows


def main() -> None:
    env_token = os.getenv("NOTION_TOKEN", "")
    presets = load_presets()
    pending_preset_name = st.session_state.pop("pending_preset_name", None)
    if pending_preset_name:
        preset = presets.get(pending_preset_name)
        if preset:
            token_for_schema = st.session_state.get("token_input", "") or env_token
            apply_preset_to_state(pending_preset_name, preset, token_for_schema)
        else:
            st.session_state["preset_notice"] = ("warning", f"`{pending_preset_name}` 프리셋을 찾지 못했습니다.")

    st.session_state.setdefault("notion_version", os.getenv("NOTION_VERSION", "2025-09-03"))
    st.session_state.setdefault("export_dir", os.getenv("EXPORT_DIR", "exports"))
    st.session_state.setdefault("db_url", "")
    st.session_state.setdefault("wizard_step", 1)

    st.title("Notion DB to Markdown")
    st.caption(f"실행 중인 버전: {APP_VERSION}")
    st.caption("Notion DB를 조회해서 선택한 페이지의 본문과 댓글을 Markdown으로 저장합니다.")

    with st.sidebar:
        st.subheader("프리셋")
        preset_names = sorted(presets)
        if preset_names:
            if st.session_state.get("preset_to_load") not in preset_names:
                st.session_state.pop("preset_to_load", None)
            selected_preset_name = selectbox_with_state("프리셋 선택", preset_names, key="preset_to_load")
            load_col, delete_col = st.columns(2)
            if load_col.button("불러오기", width="stretch"):
                st.session_state["pending_preset_name"] = selected_preset_name
                st.rerun()
            if delete_col.button("삭제", width="stretch"):
                presets.pop(selected_preset_name, None)
                save_presets(presets)
                st.session_state.pop("preset_to_load", None)
                st.session_state["preset_notice"] = ("success", f"`{selected_preset_name}` 프리셋을 삭제했습니다.")
                st.rerun()
        else:
            st.caption("저장된 프리셋이 없습니다.")

        preset_notice = st.session_state.pop("preset_notice", None)
        if preset_notice:
            notice_type, message = preset_notice
            getattr(st, notice_type)(message)

        st.divider()
        st.subheader("앱 설정")
        token_input = st.text_input(
            "Notion API token",
            type="password",
            key="token_input",
            placeholder="환경변수 토큰 사용 중" if env_token else "",
            help="비워두면 .env의 NOTION_TOKEN을 사용합니다. 입력값은 앱에 저장하지 않습니다.",
        )
        token = token_input or env_token
        if env_token and not token_input:
            st.caption(".env의 NOTION_TOKEN을 사용합니다.")
        notion_version = st.text_input("Notion API version", key="notion_version")
        export_dir = st.text_input("저장 폴더", key="export_dir")

    wizard_step = int(st.session_state.get("wizard_step", 1))
    if wizard_step not in WIZARD_STEPS:
        set_wizard_step(1)
        wizard_step = 1
    render_wizard_header(wizard_step)

    data_sources = st.session_state.get("data_sources", [])
    properties = st.session_state.get("data_source_schema", {})

    if wizard_step == 1:
        db_url = st.text_input("Notion DB URL 또는 data source ID", key="db_url")

        load_schema = st.button("스키마 불러오기", type="primary", disabled=not token or not db_url)
        if load_schema:
            try:
                load_schema_into_state(token, notion_version, db_url)
                clear_preview(reset_property_selection=True)
                st.success("스키마를 불러왔습니다.")
            except (ValueError, NotionAPIError) as exc:
                st.error(str(exc))

        data_sources = st.session_state.get("data_sources", [])
        properties = st.session_state.get("data_source_schema", {})

        if not data_sources or not properties:
            st.info("먼저 Notion API token과 DB URL을 입력한 뒤 스키마를 불러오세요.")
            render_wizard_nav(current_step=1, next_step=2, next_label="다음: 검색", next_disabled=True)
            return

        data_source_labels = {f"{item['name']} ({item['id']})": item["id"] for item in data_sources}
        data_source_options = list(data_source_labels.keys())
        selected_data_source_id_from_state = st.session_state.get("selected_data_source_id")
        selected_data_source_index = 0
        for index, label in enumerate(data_source_options):
            if data_source_labels[label] == selected_data_source_id_from_state:
                selected_data_source_index = index
                break
        selected_data_source_label = st.selectbox("Data source", options=data_source_options, index=selected_data_source_index)
        selected_data_source_id = data_source_labels[selected_data_source_label]

        if selected_data_source_id != st.session_state.get("selected_data_source_id"):
            try:
                client = get_client(token, notion_version)
                properties = client.retrieve_data_source(selected_data_source_id).get("properties", {})
                st.session_state["selected_data_source_id"] = selected_data_source_id
                st.session_state["data_source_schema"] = properties
                clear_preview(reset_property_selection=True)
            except NotionAPIError as exc:
                st.error(str(exc))
                return

        render_wizard_nav(current_step=1, next_step=2, next_label="다음: 검색")
        return

    if not data_sources or not properties:
        st.warning("연결 정보를 먼저 불러와야 합니다.")
        set_wizard_step(1)
        st.rerun()

    data_source_labels = {f"{item['name']} ({item['id']})": item["id"] for item in data_sources}
    data_source_options = list(data_source_labels.keys())
    selected_data_source_id = st.session_state.get("selected_data_source_id")
    if selected_data_source_id not in data_source_labels.values():
        selected_data_source_id = data_source_labels[data_source_options[0]]
        st.session_state["selected_data_source_id"] = selected_data_source_id
    selected_data_source_label = next(
        label for label, data_source_id in data_source_labels.items() if data_source_id == selected_data_source_id
    )
    db_url = st.session_state.get("db_url", "")

    if wizard_step == 2:
        left, middle, right = st.columns(3)

        with left:
            date_property = select_property(
                "기간 기준 속성",
                properties,
                {"date", "created_time", "last_edited_time"},
                "date",
                "date_property",
            )
            date_filter_mode = selectbox_with_state("날짜 필터", DATE_FILTER_MODES, key="date_filter_mode")
            start_date = None
            end_date = None
            if date_filter_mode in {"시작일 이후", "기간"}:
                start_date = optional_date_input("시작일", "start_date")
            if date_filter_mode in {"종료일 이전", "기간"}:
                end_date = optional_date_input(
                    "종료일",
                    "end_date",
                    default=start_date if date_filter_mode == "기간" else None,
                )

        with middle:
            person_property = select_property(
                "담당자 속성",
                properties,
                {"people", "created_by", "last_edited_by"},
                "person",
                "person_property",
            )
            person_terms = st.text_input("담당자 이름/이메일", placeholder="예: 홍길동, user@example.com", key="person_terms")
            keyword = st.text_input("키워드", placeholder="본문/제목/속성에서 검색, 쉼표로 AND 검색", key="keyword")
            include_body_preview = st.checkbox("본문 미리보기 포함", value=False, key="include_body_preview")

        with right:
            option_property = select_property(
                "상태/옵션 속성",
                properties,
                {"status", "select", "multi_select"},
                "option",
                "option_property",
            )
            option_value = ""
            option_property_type = None
            if option_property:
                option_property_type = properties[option_property].get("type")
                values = option_values(properties[option_property])
                if values:
                    option_value_options = ["전체"] + values
                    if st.session_state.get("option_value") not in option_value_options:
                        st.session_state["option_value"] = "전체"
                    option_value = st.selectbox("상태/옵션 값", option_value_options, key="option_value")
                    if option_value == "전체":
                        option_value = ""
                else:
                    option_value = st.text_input("상태/옵션 값", key="option_value")

            max_pages = number_input_with_state(
                "최대 페이지 수",
                key="max_pages",
                default=100,
                min_value=1,
                max_value=1000,
                step=10,
            )

        current_filter_start_date, current_filter_end_date = active_date_bounds(date_filter_mode, start_date, end_date)
        current_search_config = {
            "selected_data_source_id": selected_data_source_id,
            "date_property": date_property,
            "date_filter_mode": date_filter_mode,
            "filter_start_date": current_filter_start_date.isoformat() if current_filter_start_date else None,
            "filter_end_date": current_filter_end_date.isoformat() if current_filter_end_date else None,
            "person_property": person_property,
            "person_terms": person_terms,
            "option_property": option_property,
            "option_value": option_value,
            "keyword": keyword,
            "max_pages": int(max_pages),
            "include_body_preview": include_body_preview,
        }

        with st.sidebar:
            st.divider()
            st.subheader("프리셋 저장")
            preset_save_name = st.text_input("프리셋 이름", key="preset_save_name", placeholder="예: 주간 회의록")
            save_preset = st.button(
                "현재 설정 저장",
                disabled=not db_url or not preset_save_name.strip(),
                width="stretch",
            )
            if save_preset:
                presets[preset_save_name.strip()] = current_preset_payload(
                    db_url=db_url,
                    notion_version=notion_version,
                    export_dir=export_dir,
                    selected_data_source_id=selected_data_source_id,
                )
                save_presets(presets)
                st.session_state["preset_notice"] = ("success", f"`{preset_save_name.strip()}` 프리셋을 저장했습니다.")
                st.rerun()
            st.caption("프리셋에는 토큰을 저장하지 않습니다.")

        run_preview = st.button("미리 조회", type="primary")

        if run_preview:
            clear_preview()
            date_validation_error = validate_date_filter(date_filter_mode, date_property, start_date, end_date)
            if date_validation_error:
                st.error(date_validation_error)
                render_wizard_nav(
                    current_step=2,
                    previous_step=1,
                    next_step=3,
                    next_label="다음: 내보내기",
                    next_disabled=True,
                )
                return

            filter_start_date, filter_end_date = current_filter_start_date, current_filter_end_date
            try:
                client = get_client(token, notion_version)
                api_filter = build_api_filter(
                    date_property=date_property,
                    date_property_type=properties[date_property].get("type") if date_property else None,
                    start_date=filter_start_date,
                    end_date=filter_end_date,
                    option_property=option_property,
                    option_property_type=option_property_type,
                    option_value=option_value,
                )
                pages = client.query_data_source(
                    selected_data_source_id,
                    filter_payload=api_filter,
                    max_pages=int(max_pages),
                )
            except NotionAPIError as exc:
                st.error(str(exc))
                render_wizard_nav(
                    current_step=2,
                    previous_step=1,
                    next_step=3,
                    next_label="다음: 내보내기",
                    next_disabled=True,
                )
                return

            preview_pages = []
            preview_rows = []
            skipped = 0
            warnings: list[str] = []
            issues: list[dict[str, str]] = []
            person_terms_list = comma_terms(person_terms)

            if pages:
                progress = st.progress(0)
                status = st.empty()
            else:
                progress = None
                status = None

            for index, page in enumerate(pages, start=1):
                if status:
                    status.write(f"미리 조회 중: {index}/{len(pages)} {page_title(page)}")

                if not person_filter_matches(page, person_property, person_terms_list):
                    skipped += 1
                    if progress:
                        progress.progress(index / len(pages))
                    continue

                body_markdown = ""
                should_fetch_body = bool(keyword and keyword.strip()) or include_body_preview
                if should_fetch_body:
                    try:
                        body_markdown, body_warnings = get_cached_body(client, page["id"])
                        warnings.extend(body_warnings)
                        issues.extend(warning_records(page, "본문 조회", body_warnings))
                    except NotionAPIError as exc:
                        skipped += 1
                        issues.append(issue_record(page, "본문 조회", exc))
                        if progress:
                            progress.progress(index / len(pages))
                        continue

                if not keyword_matches(page, body_markdown, keyword):
                    skipped += 1
                    if progress:
                        progress.progress(index / len(pages))
                    continue

                preview_pages.append(page)
                preview_rows.append(
                    preview_row(
                        page,
                        date_property=date_property,
                        person_property=person_property,
                        option_property=option_property,
                        body_preview=body_preview_text(body_markdown) if should_fetch_body else "",
                    )
                )
                if progress:
                    progress.progress(index / len(pages))

            if status:
                status.write("미리 조회 완료")

            st.session_state["preview_pages"] = preview_pages
            st.session_state["preview_rows"] = preview_rows
            st.session_state["preview_warnings"] = warnings
            st.session_state["preview_issues"] = issues
            st.session_state["preview_skipped"] = skipped
            st.session_state["preview_total"] = len(pages)
            st.session_state["preview_config"] = current_search_config


        preview_total_for_nav = st.session_state.get("preview_total")
        preview_matches_current_search = (
            preview_total_for_nav is not None
            and st.session_state.get("preview_config", {}) == current_search_config
        )
        if preview_matches_current_search:
            st.success(
                f"미리 조회 완료: {len(st.session_state.get('preview_rows', []))}개 페이지가 내보내기 후보입니다."
            )
        elif preview_total_for_nav is not None:
            st.warning("검색 조건이 변경되었습니다. 미리 조회를 다시 실행해 주세요.")
        render_wizard_nav(
            current_step=2,
            previous_step=1,
            next_step=3,
            next_label="다음: 내보내기",
            next_disabled=not preview_matches_current_search,
        )
        return

    # Step 3: export

    preview_rows = st.session_state.get("preview_rows", [])
    preview_pages = st.session_state.get("preview_pages", [])
    preview_warnings = st.session_state.get("preview_warnings", [])
    preview_issues = st.session_state.get("preview_issues", [])
    preview_config = st.session_state.get("preview_config", {})
    preview_total = st.session_state.get("preview_total")
    preview_skipped = st.session_state.get("preview_skipped", 0)
    person_terms = st.session_state.get("person_terms", "")
    option_value = st.session_state.get("option_value", "")
    if option_value == "전체":
        option_value = ""
    keyword = st.session_state.get("keyword", "")
    max_pages = st.session_state.get("max_pages", 100)

    if preview_total is None:
        st.info("검색 조건을 정한 뒤 `미리 조회`를 누르면 결과를 확인하고 저장할 수 있습니다.")
        render_wizard_nav(current_step=3, previous_step=2)
        return

    st.write(f"조회된 페이지: {preview_total}")
    st.write(f"미리보기 대상: {len(preview_rows)}")
    st.write(f"로컬 필터로 제외된 페이지: {preview_skipped}")
    if preview_config.get("date_filter_mode") and preview_config.get("date_filter_mode") != "전체":
        applied_parts = [
            f"속성: {preview_config.get('date_property') or '-'}",
            f"모드: {preview_config.get('date_filter_mode')}",
        ]
        if preview_config.get("filter_start_date"):
            applied_parts.append(f"시작일: {preview_config['filter_start_date']}")
        if preview_config.get("filter_end_date"):
            applied_parts.append(f"종료일: {preview_config['filter_end_date']}")
        st.caption("적용된 날짜 조건: " + " / ".join(applied_parts))

    if preview_warnings:
        with st.expander("미리 조회 경고"):
            for warning in preview_warnings:
                st.warning(warning)

    if preview_issues:
        preview_error_count = sum(1 for issue in preview_issues if issue.get("severity") == "error")
        preview_warning_count = sum(1 for issue in preview_issues if issue.get("severity") == "warning")
        st.write(f"미리 조회 이슈: 실패 {preview_error_count}, 경고 {preview_warning_count}")
        st.dataframe(
            preview_issues,
            column_config={
                "severity": "구분",
                "step": "단계",
                "title": "제목",
                "message": "메시지",
                "url": st.column_config.LinkColumn("Notion"),
                "page_id": None,
            },
            width="stretch",
            hide_index=True,
        )

    if not preview_rows:
        st.warning("조건에 맞는 페이지가 없습니다.")
        render_wizard_nav(current_step=3, previous_step=2)
        return

    filename_style_label = selectbox_with_state(
        "파일명 형식",
        list(FILENAME_STYLE_OPTIONS.keys()),
        key="filename_style_label",
    )
    filename_style = FILENAME_STYLE_OPTIONS[filename_style_label]

    filename_requirements = {
        "date_title": [("date_property", "기간 기준 속성")],
        "option_title": [("option_property", "상태/옵션 속성")],
        "person_title": [("person_property", "담당자 속성")],
        "date_option_title": [("date_property", "기간 기준 속성"), ("option_property", "상태/옵션 속성")],
    }
    missing_parts = [
        label
        for key, label in filename_requirements.get(filename_style, [])
        if not preview_config.get(key)
    ]
    if missing_parts:
        st.caption(f"`{filename_style_label}` 형식에서 {', '.join(missing_parts)} 값이 없으면 해당 항목은 생략됩니다.")

    rows_for_editor = preview_rows_with_filenames(
        preview_rows,
        preview_pages,
        filename_style=filename_style,
        date_property=preview_config.get("date_property"),
        person_property=preview_config.get("person_property"),
        option_property=preview_config.get("option_property"),
    )
    show_body_preview = any(row.get("body_preview") for row in rows_for_editor)
    preview_column_config = {
        "export": st.column_config.CheckboxColumn("저장", default=True),
        "title": "제목",
        "expected_filename": "예상 파일명",
        "body_preview": "본문 미리보기" if show_body_preview else None,
        "date": "기간",
        "assignee": "담당자",
        "status": "상태",
        "last_edited": "마지막 수정",
        "url": st.column_config.LinkColumn("Notion"),
        "page_id": None,
    }

    edited_rows = st.data_editor(
        rows_for_editor,
        column_config=preview_column_config,
        disabled=["title", "expected_filename", "body_preview", "date", "assignee", "status", "last_edited", "url", "page_id"],
        hide_index=True,
        width="stretch",
        key="preview_editor_with_filename",
    )
    selected_ids = selected_preview_page_ids(edited_rows)

    st.write("Markdown 구성")
    comments_only_export = st.checkbox("댓글만 저장 (본문 제외)", value=False, key="comments_only_export")
    format_left, format_middle, format_right = st.columns(3)
    with format_left:
        include_frontmatter = st.checkbox("YAML frontmatter 포함", value=True, key="include_frontmatter")
        include_source_url = st.checkbox("원본 Notion URL 표시", value=False, key="include_source_url")
    with format_middle:
        include_properties = st.checkbox("Properties 표 포함", value=True, key="include_properties")
    with format_right:
        include_comments_section = st.checkbox("댓글 섹션 포함", value=True, key="include_comments_section")
        omit_empty_comments = st.checkbox(
            "댓글 없으면 Comments 생략",
            value=True,
            key="omit_empty_comments",
            disabled=not include_comments_section,
        )
        only_pages_with_comments = st.checkbox("댓글 있는 페이지만 저장", value=False, key="only_pages_with_comments")

    should_query_comments = include_comments_section or only_pages_with_comments or comments_only_export
    effective_include_comments = include_comments_section or comments_only_export
    effective_only_pages_with_comments = only_pages_with_comments or comments_only_export
    export_left, export_right = st.columns(2)
    with export_left:
        comment_scope = st.radio(
            "댓글 범위",
            ["페이지 댓글만", "페이지 + 본문 블록 댓글"],
            horizontal=True,
            key="comment_scope",
            disabled=not should_query_comments,
        )
    with export_right:
        max_comment_blocks = number_input_with_state(
            "페이지당 댓글 조회 블록 수",
            key="max_comment_blocks",
            default=300,
            min_value=0,
            max_value=2000,
            step=50,
            disabled=not should_query_comments or comment_scope == "페이지 댓글만",
        )

    if comments_only_export:
        st.caption("댓글만 저장하면 본문 조회와 Body 섹션을 건너뛰고, 댓글이 있는 페이지만 저장합니다.")
    elif only_pages_with_comments and not include_comments_section:
        st.caption("댓글 섹션은 끄고 댓글 여부만 확인합니다. 댓글이 있는 페이지의 본문만 저장됩니다.")
    elif not include_comments_section:
        st.caption("댓글 섹션을 끄면 댓글 API 조회를 건너뜁니다.")
    if should_query_comments and comment_scope == "페이지 + 본문 블록 댓글":
        st.caption("본문 블록 댓글까지 조회하면 페이지 수와 블록 수에 따라 시간이 더 걸릴 수 있습니다.")

    run_export = st.button(
        f"선택한 {len(selected_ids)}개 페이지 Markdown 저장",
        type="primary",
        disabled=not selected_ids,
    )
    if run_export:
        output_dir = Path(export_dir) / f"notion-export-{now_stamp()}"
        results = []
        warnings: list[str] = []
        issues: list[dict[str, str]] = []
        files: list[Path] = []
        skipped_no_comments = 0
        skipped_comment_lookup_failed = 0
        selected_pages = [page for page in preview_pages if page.get("id") in selected_ids]

        progress = st.progress(0)
        status = st.empty()
        client = get_client(token, notion_version)

        for index, page in enumerate(selected_pages, start=1):
            status.write(f"저장 중: {index}/{len(selected_pages)} {page_title(page)}")
            comments = []
            if should_query_comments:
                try:
                    comments = client.list_page_comments(
                        page["id"],
                        include_descendant_blocks=comment_scope == "페이지 + 본문 블록 댓글",
                        max_blocks=int(max_comment_blocks),
                    )
                except NotionAPIError as exc:
                    issues.append(issue_record(page, "댓글 조회", exc, "warning"))
                    if effective_only_pages_with_comments:
                        skipped_comment_lookup_failed += 1
                        progress.progress(index / len(selected_pages))
                        continue

            if effective_only_pages_with_comments and not comments:
                skipped_no_comments += 1
                progress.progress(index / len(selected_pages))
                continue

            body_markdown = ""
            if not comments_only_export:
                try:
                    body_markdown, body_warnings = get_cached_body(client, page["id"])
                    warnings.extend(body_warnings)
                    issues.extend(warning_records(page, "본문 조회", body_warnings))
                except NotionAPIError as exc:
                    issues.append(issue_record(page, "본문 조회", exc))
                    progress.progress(index / len(selected_pages))
                    continue

            try:
                result = write_markdown_file(
                    page,
                    body_markdown,
                    comments,
                    output_dir,
                    filename_style=filename_style,
                    date_property=preview_config.get("date_property"),
                    person_property=preview_config.get("person_property"),
                    option_property=preview_config.get("option_property"),
                    include_frontmatter=include_frontmatter,
                    include_properties=include_properties,
                    include_body=not comments_only_export,
                    include_comments=effective_include_comments,
                    omit_empty_comments=omit_empty_comments,
                    include_source_url=include_source_url,
                )
                results.append(result)
                files.append(result.file_path)
            except OSError as exc:
                issues.append(issue_record(page, "파일 저장", exc))
            progress.progress(index / len(selected_pages))

        status.write("저장 완료")
        st.session_state["export_results"] = results
        st.session_state["export_files"] = files
        st.session_state["export_output_dir"] = output_dir
        st.session_state["export_warnings"] = warnings
        st.session_state["export_issues"] = issues
        st.session_state["export_skipped_no_comments"] = skipped_no_comments
        st.session_state["export_skipped_comment_lookup_failed"] = skipped_comment_lookup_failed

        summary_metadata = {
            "DB URL": db_url,
            "Data source": selected_data_source_label,
            "Notion API version": notion_version,
            "Date property": preview_config.get("date_property"),
            "Date filter": preview_config.get("date_filter_mode", "전체"),
            "Filter start date": preview_config.get("filter_start_date"),
            "Filter end date": preview_config.get("filter_end_date"),
            "Person property": preview_config.get("person_property"),
            "Person terms": person_terms,
            "Option property": preview_config.get("option_property"),
            "Option value": option_value or "전체",
            "Keyword": keyword,
            "Max pages": max_pages,
            "Preview total": preview_total,
            "Preview skipped": preview_skipped,
            "Selected pages": len(selected_pages),
            "Filename style": filename_style_label,
            "YAML frontmatter": include_frontmatter,
            "Properties table": include_properties,
            "Source URL in body": include_source_url,
            "Comments section": effective_include_comments,
            "Comments only export": comments_only_export,
            "Omit empty comments": omit_empty_comments,
            "Only pages with comments": effective_only_pages_with_comments,
            "Skipped without comments": skipped_no_comments,
            "Skipped comment lookup failed": skipped_comment_lookup_failed,
            "Comment scope": comment_scope if should_query_comments else "댓글 조회 안 함",
            "Max comment blocks": max_comment_blocks if should_query_comments else "",
        }
        try:
            summary_path = write_export_summary_file(
                output_dir,
                metadata=summary_metadata,
                results=results,
                issues=issues,
            )
            files.append(summary_path)
            st.session_state["export_summary_path"] = summary_path
        except OSError as exc:
            issues.append(
                {
                    "severity": "warning",
                    "step": "요약 파일 저장",
                    "title": "_export_summary.md",
                    "message": exception_message(exc),
                    "url": "",
                    "page_id": "",
                }
            )
            st.session_state["export_issues"] = issues
        st.session_state["export_files"] = files

    results = st.session_state.get("export_results", [])
    files = st.session_state.get("export_files", [])
    output_dir = st.session_state.get("export_output_dir")
    summary_path = st.session_state.get("export_summary_path")
    export_warnings = st.session_state.get("export_warnings", [])
    export_issues = st.session_state.get("export_issues", [])
    skipped_no_comments = st.session_state.get("export_skipped_no_comments", 0)
    skipped_comment_lookup_failed = st.session_state.get("export_skipped_comment_lookup_failed", 0)

    if not results and not export_issues and not skipped_no_comments and not skipped_comment_lookup_failed:
        render_wizard_nav(current_step=3, previous_step=2)
        return

    st.subheader("저장 결과")
    success_count = len(results)
    error_count = sum(1 for issue in export_issues if issue.get("severity") == "error")
    warning_count = sum(1 for issue in export_issues if issue.get("severity") == "warning")
    summary_cols = st.columns(4)
    summary_cols[0].metric("저장 성공", success_count)
    summary_cols[1].metric("실패", error_count)
    summary_cols[2].metric("경고", warning_count)
    summary_cols[3].metric("댓글 조건 제외", skipped_no_comments + skipped_comment_lookup_failed)
    if skipped_no_comments or skipped_comment_lookup_failed:
        st.caption(
            f"댓글 없음 {skipped_no_comments}개"
            + (f", 댓글 조회 실패 {skipped_comment_lookup_failed}개" if skipped_comment_lookup_failed else "")
        )
    if output_dir:
        st.write("저장 폴더")
        st.code(str(Path(output_dir).resolve()), language=None)
    if summary_path:
        st.write(f"요약 파일: `{Path(summary_path).name}`")

    if export_warnings:
        with st.expander("저장 경고"):
            for warning in export_warnings:
                st.warning(warning)

    if export_issues:
        st.write("이슈")
        st.dataframe(
            export_issues,
            column_config={
                "severity": "구분",
                "step": "단계",
                "title": "제목",
                "message": "메시지",
                "url": st.column_config.LinkColumn("Notion"),
                "page_id": None,
            },
            width="stretch",
            hide_index=True,
        )

    if results:
        st.write("저장된 파일")
        st.dataframe(
            [
                {
                    "제목": result.title,
                    "댓글": result.comments_count,
                    "파일명": result.file_path.name,
                    "경로": str(result.file_path),
                    "Notion": result.url,
                }
                for result in results
            ],
            column_config={"Notion": st.column_config.LinkColumn("Notion")},
            width="stretch",
        )
        st.download_button(
            "ZIP 다운로드",
            data=create_zip_bytes(files),
            file_name=f"{Path(output_dir).name}.zip",
            mime="application/zip",
        )

    render_wizard_nav(current_step=3, previous_step=2)


if __name__ == "__main__":
    try:
        main()
    finally:
        render_app_footer()
