from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import ensure_dir


@dataclass
class ExportResult:
    title: str
    page_id: str
    url: str
    file_path: Path
    comments_count: int


def plain_text(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    return "".join(item.get("plain_text") or item.get("text", {}).get("content") or "" for item in items)


def page_title(page: dict[str, Any]) -> str:
    for value in page.get("properties", {}).values():
        if value.get("type") == "title":
            title = plain_text(value.get("title"))
            if title:
                return title
    return "Untitled"


def property_to_text(value: dict[str, Any]) -> str:
    prop_type = value.get("type")
    data = value.get(prop_type)

    if prop_type == "title":
        return plain_text(data)
    if prop_type == "rich_text":
        return plain_text(data)
    if prop_type in {"select", "status"}:
        return (data or {}).get("name", "")
    if prop_type == "multi_select":
        return ", ".join(item.get("name", "") for item in data or [])
    if prop_type == "date":
        if not data:
            return ""
        start = data.get("start", "")
        end = data.get("end")
        return f"{start} - {end}" if end else start
    if prop_type == "people":
        return ", ".join(person_to_text(person) for person in data or [])
    if prop_type in {"url", "email", "phone_number", "number", "checkbox", "created_time", "last_edited_time"}:
        return "" if data is None else str(data)
    if prop_type == "created_by" or prop_type == "last_edited_by":
        return person_to_text(data or {})
    if prop_type == "files":
        return ", ".join(item.get("name") or item.get("file", {}).get("url") or item.get("external", {}).get("url", "") for item in data or [])
    if prop_type == "relation":
        return ", ".join(item.get("id", "") for item in data or [])
    if prop_type == "formula":
        return formula_to_text(data or {})
    if prop_type == "rollup":
        return rollup_to_text(data or {})
    if prop_type == "unique_id":
        prefix = (data or {}).get("prefix")
        number = (data or {}).get("number")
        return f"{prefix}-{number}" if prefix else ("" if number is None else str(number))

    return ""


def compact_datetime_for_filename(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return sanitize_filename_part(raw, max_length=32)

    if "T" not in raw and parsed.time() == datetime.min.time():
        return parsed.strftime("%Y-%m-%d")
    return parsed.strftime("%Y-%m-%d_%H-%M")


def compact_date_property_for_filename(value: dict[str, Any]) -> str:
    prop_type = value.get("type")
    if prop_type == "date":
        data = value.get("date") or {}
        start = compact_datetime_for_filename(data.get("start", ""))
        end = compact_datetime_for_filename(data.get("end", ""))
        if start and end and start != end:
            return f"{start}_to_{end}"
        return start

    if prop_type in {"created_time", "last_edited_time"}:
        return compact_datetime_for_filename(str(value.get(prop_type) or ""))

    rendered = property_to_text(value)
    return sanitize_filename_part(rendered, max_length=32)


def person_to_text(person: dict[str, Any]) -> str:
    name = person.get("name") or ""
    email = person.get("person", {}).get("email") or ""
    if name and email:
        return f"{name} <{email}>"
    return name or email or person.get("id", "")


def formula_to_text(formula: dict[str, Any]) -> str:
    formula_type = formula.get("type")
    value = formula.get(formula_type)
    if formula_type == "date" and isinstance(value, dict):
        return property_to_text({"type": "date", "date": value})
    return "" if value is None else str(value)


def rollup_to_text(rollup: dict[str, Any]) -> str:
    rollup_type = rollup.get("type")
    value = rollup.get(rollup_type)
    if rollup_type == "array":
        return ", ".join(property_to_text(item) for item in value or [])
    return "" if value is None else str(value)


def sanitize_filename_part(value: str, *, max_length: int = 80) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\n\r\t]+", " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    return cleaned[:max_length].strip()


def slugify_filename(title: str, page_id: str) -> str:
    cleaned = sanitize_filename_part(title)
    if not cleaned:
        cleaned = "untitled"
    short_id = page_id.replace("-", "")[:8]
    return f"{cleaned}-{short_id}.md" if short_id else f"{cleaned}.md"


def page_property_text(page: dict[str, Any], property_name: str | None) -> str:
    if not property_name:
        return ""
    value = page.get("properties", {}).get(property_name)
    return property_to_text(value) if value else ""


def page_property_filename_date(page: dict[str, Any], property_name: str | None) -> str:
    if not property_name:
        return ""
    value = page.get("properties", {}).get(property_name)
    return compact_date_property_for_filename(value) if value else ""


def build_export_filename(
    page: dict[str, Any],
    *,
    filename_style: str = "title_id",
    date_property: str | None = None,
    person_property: str | None = None,
    option_property: str | None = None,
) -> str:
    title = sanitize_filename_part(page_title(page)) or "untitled"
    page_id = page.get("id", "")
    short_id = page_id.replace("-", "")[:8]

    if filename_style == "title_id":
        return slugify_filename(title, page_id)

    date_text = sanitize_filename_part(page_property_filename_date(page, date_property), max_length=40)
    person_text = sanitize_filename_part(page_property_text(page, person_property), max_length=32)
    option_text = sanitize_filename_part(page_property_text(page, option_property), max_length=32)

    if filename_style == "title":
        parts = [title]
    elif filename_style == "date_title":
        parts = [date_text, title]
    elif filename_style == "option_title":
        parts = [option_text, title]
    elif filename_style == "person_title":
        parts = [person_text, title]
    elif filename_style == "date_option_title":
        parts = [date_text, option_text, title]
    else:
        parts = [title, short_id]

    filename_body = "_".join(part for part in parts if part)
    if not filename_body:
        filename_body = f"untitled_{short_id}" if short_id else "untitled"
    return f"{filename_body[:120].strip()}.md"


def unique_file_path(file_path: Path) -> Path:
    if not file_path.exists():
        return file_path

    stem = file_path.stem
    suffix = file_path.suffix
    parent = file_path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def markdown_table_row(left: str, right: str) -> str:
    safe_left = left.replace("|", "\\|").replace("\n", " ")
    safe_right = right.replace("|", "\\|").replace("\n", "<br>")
    return f"| {safe_left} | {safe_right} |"


def comments_to_markdown(comments: list[dict[str, Any]]) -> str:
    if not comments:
        return "_댓글 없음_"

    lines: list[str] = []
    for index, comment in enumerate(comments, start=1):
        author = person_to_text(comment.get("created_by") or {})
        created_time = comment.get("created_time", "")
        block_id = comment.get("_source_block_id", "")
        rich_text = plain_text(comment.get("rich_text"))

        lines.extend(
            [
                f"### Comment {index}",
                "",
                f"- Author: {author or 'Unknown'}",
                f"- Created: {created_time}",
                f"- Block: `{block_id}`" if block_id else "- Block: ",
                "",
                rich_text or "_내용 없음_",
                "",
            ]
        )
    return "\n".join(lines).strip()


def compose_page_markdown(
    page: dict[str, Any],
    body_markdown: str,
    comments: list[dict[str, Any]],
    *,
    include_frontmatter: bool = True,
    include_properties: bool = True,
    include_body: bool = True,
    include_comments: bool = True,
    omit_empty_comments: bool = False,
    include_source_url: bool = False,
) -> str:
    title = page_title(page)
    properties = page.get("properties", {})
    exported_at = datetime.now(timezone.utc).astimezone().isoformat()

    lines: list[str] = []
    if include_frontmatter:
        lines.extend(
            [
                "---",
                f"notion_id: {page.get('id', '')}",
                f"notion_url: {page.get('url', '')}",
                f"created_time: {page.get('created_time', '')}",
                f"last_edited_time: {page.get('last_edited_time', '')}",
                f"exported_at: {exported_at}",
                "---",
                "",
            ]
        )

    lines.extend([f"# {title}", ""])

    if include_source_url and page.get("url"):
        lines.extend([f"[원본 Notion 페이지]({page['url']})", ""])

    if include_properties:
        lines.extend(["## Properties", "", "| Property | Value |", "| --- | --- |"])
        for name, value in sorted(properties.items()):
            rendered = property_to_text(value)
            if rendered:
                lines.append(markdown_table_row(name, rendered))
        lines.append("")

    if include_body:
        lines.extend(["## Body", "", body_markdown.strip() or "_본문 없음_", ""])

    if include_comments and (comments or not omit_empty_comments):
        lines.extend(["## Comments", "", comments_to_markdown(comments), ""])

    return "\n".join(lines)


def write_markdown_file(
    page: dict[str, Any],
    body_markdown: str,
    comments: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    filename_style: str = "title_id",
    date_property: str | None = None,
    person_property: str | None = None,
    option_property: str | None = None,
    include_frontmatter: bool = True,
    include_properties: bool = True,
    include_body: bool = True,
    include_comments: bool = True,
    omit_empty_comments: bool = False,
    include_source_url: bool = False,
) -> ExportResult:
    directory = ensure_dir(output_dir)
    title = page_title(page)
    filename = build_export_filename(
        page,
        filename_style=filename_style,
        date_property=date_property,
        person_property=person_property,
        option_property=option_property,
    )
    file_path = unique_file_path(directory / filename)
    markdown = compose_page_markdown(
        page,
        body_markdown,
        comments,
        include_frontmatter=include_frontmatter,
        include_properties=include_properties,
        include_body=include_body,
        include_comments=include_comments,
        omit_empty_comments=omit_empty_comments,
        include_source_url=include_source_url,
    )
    file_path.write_text(markdown, encoding="utf-8")
    return ExportResult(
        title=title,
        page_id=page.get("id", ""),
        url=page.get("url", ""),
        file_path=file_path,
        comments_count=len(comments),
    )


def create_zip_bytes(files: list[Path]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)
    buffer.seek(0)
    return buffer.read()


def summary_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def summary_table(rows: list[tuple[str, Any]]) -> list[str]:
    lines = ["| Field | Value |", "| --- | --- |"]
    for field, value in rows:
        lines.append(f"| {summary_cell(field)} | {summary_cell(value)} |")
    return lines


def write_export_summary_file(
    output_dir: str | Path,
    *,
    metadata: dict[str, Any],
    results: list[ExportResult],
    issues: list[dict[str, str]],
    skipped_pages: list[dict[str, str]] | None = None,
) -> Path:
    directory = ensure_dir(output_dir)
    summary_path = directory / "_export_summary.md"
    exported_at = datetime.now(timezone.utc).astimezone().isoformat()
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    skipped_pages = skipped_pages or []

    lines = [
        "# Export Summary",
        "",
        "## Overview",
        "",
        *summary_table(
            [
                ("Exported at", exported_at),
                ("Saved pages", len(results)),
                ("Errors", error_count),
                ("Warnings", warning_count),
                ("Output directory", directory.resolve()),
            ]
        ),
        "",
        "## Settings",
        "",
        *summary_table(list(metadata.items())),
        "",
        "## Files",
        "",
        "| Title | File | Comments | Notion |",
        "| --- | --- | --- | --- |",
    ]

    if results:
        for result in results:
            lines.append(
                "| "
                f"{summary_cell(result.title)} | "
                f"{summary_cell(result.file_path.name)} | "
                f"{summary_cell(result.comments_count)} | "
                f"{summary_cell(result.url)} |"
            )
    else:
        lines.append("| _No files saved_ |  |  |  |")

    lines.extend(["", "## Skipped Pages", "", "| Reason | Title | Notion |", "| --- | --- | --- |"])
    if skipped_pages:
        for skipped_page in skipped_pages:
            lines.append(
                "| "
                f"{summary_cell(skipped_page.get('reason', ''))} | "
                f"{summary_cell(skipped_page.get('title', ''))} | "
                f"{summary_cell(skipped_page.get('url', ''))} |"
            )
    else:
        lines.append("| _None_ |  |  |")

    lines.extend(["", "## Issues", "", "| Severity | Step | Title | Message | Notion |", "| --- | --- | --- | --- | --- |"])
    if issues:
        for issue in issues:
            lines.append(
                "| "
                f"{summary_cell(issue.get('severity', ''))} | "
                f"{summary_cell(issue.get('step', ''))} | "
                f"{summary_cell(issue.get('title', ''))} | "
                f"{summary_cell(issue.get('message', ''))} | "
                f"{summary_cell(issue.get('url', ''))} |"
            )
    else:
        lines.append("| _None_ |  |  |  |  |")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path
