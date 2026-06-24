from pathlib import Path

from notion_to_md.exporter import (
    build_export_filename,
    compact_datetime_for_filename,
    compose_page_markdown,
    property_to_text,
    unique_file_path,
)


def make_page(*, title="Hello / World", page_id="12345678-1234-1234-1234-123456789abc", extra_props=None):
    properties = {
        "Name": {"type": "title", "title": [{"plain_text": title}]},
    }
    if extra_props:
        properties.update(extra_props)
    return {"id": page_id, "properties": properties}


def test_build_export_filename_title_id_sanitizes_title_and_appends_short_id():
    page = make_page(title='Bad / Name: With * Chars?')

    assert build_export_filename(page, filename_style="title_id") == "Bad Name With Chars-12345678.md"


def test_build_export_filename_uses_date_option_and_title_parts():
    page = make_page(
        title="Launch Plan",
        extra_props={
            "Due": {"type": "date", "date": {"start": "2026-06-24T09:30:00.000Z"}},
            "Status": {"type": "status", "status": {"name": "In Progress"}},
        },
    )

    assert (
        build_export_filename(
            page,
            filename_style="date_option_title",
            date_property="Due",
            option_property="Status",
        )
        == "2026-06-24_09-30_In Progress_Launch Plan.md"
    )


def test_compact_datetime_for_filename_handles_dates_and_datetimes():
    assert compact_datetime_for_filename("2026-06-24") == "2026-06-24"
    assert compact_datetime_for_filename("2026-06-24T15:45:10Z") == "2026-06-24_15-45"


def test_unique_file_path_appends_incrementing_suffix(tmp_path: Path):
    existing = tmp_path / "export.md"
    existing.write_text("first", encoding="utf-8")
    (tmp_path / "export-2.md").write_text("second", encoding="utf-8")

    assert unique_file_path(existing) == tmp_path / "export-3.md"


def test_property_to_text_renders_people_and_multi_select():
    people_text = property_to_text(
        {
            "type": "people",
            "people": [
                {"name": "Alice", "person": {"email": "alice@example.com"}},
                {"name": "Bob", "person": {}},
            ],
        }
    )
    multi_select_text = property_to_text(
        {
            "type": "multi_select",
            "multi_select": [{"name": "Docs"}, {"name": "Export"}],
        }
    )

    assert people_text == "Alice <alice@example.com>, Bob"
    assert multi_select_text == "Docs, Export"


def test_compose_page_markdown_can_export_comments_without_body():
    page = {
        "id": "12345678-1234-1234-1234-123456789abc",
        "url": "https://notion.so/example",
        "properties": {"Name": {"type": "title", "title": [{"plain_text": "Commented Page"}]}},
    }
    markdown = compose_page_markdown(
        page,
        "This body should not be included",
        [
            {
                "created_by": {"name": "Reviewer"},
                "created_time": "2026-06-24T10:00:00Z",
                "_source_block_id": "block-id",
                "rich_text": [{"plain_text": "Please update this section."}],
            }
        ],
        include_properties=False,
        include_body=False,
        include_comments=True,
    )

    assert "## Body" not in markdown
    assert "This body should not be included" not in markdown
    assert "## Comments" in markdown
    assert "Please update this section." in markdown
