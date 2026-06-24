from datetime import date

from notion_to_md.filters import build_api_filter, keyword_matches, person_filter_matches


def make_page():
    return {
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "Quarterly Export Notes"}]},
            "Owner": {
                "type": "people",
                "people": [
                    {"name": "Jane Doe", "person": {"email": "jane@example.com"}},
                ],
            },
            "Status": {"type": "status", "status": {"name": "Done"}},
        }
    }


def test_build_api_filter_combines_date_and_status_filters():
    assert build_api_filter(
        date_property="Due",
        date_property_type="date",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        option_property="Status",
        option_property_type="status",
        option_value="Done",
    ) == {
        "and": [
            {"property": "Due", "date": {"on_or_after": "2026-06-01"}},
            {"property": "Due", "date": {"on_or_before": "2026-06-30"}},
            {"property": "Status", "status": {"equals": "Done"}},
        ]
    }


def test_build_api_filter_uses_created_time_filter_key():
    assert build_api_filter(
        date_property="Created time",
        date_property_type="created_time",
        start_date=date(2026, 6, 24),
    ) == {"property": "Created time", "created_time": {"on_or_after": "2026-06-24"}}


def test_build_api_filter_handles_select_and_multi_select_options():
    select_filter = build_api_filter(
        option_property="Type",
        option_property_type="select",
        option_value="Article",
    )
    multi_select_filter = build_api_filter(
        option_property="Tags",
        option_property_type="multi_select",
        option_value="Docs",
    )

    assert select_filter == {"property": "Type", "select": {"equals": "Article"}}
    assert multi_select_filter == {"property": "Tags", "multi_select": {"contains": "Docs"}}


def test_person_filter_matches_name_or_email_terms():
    page = make_page()

    assert person_filter_matches(page, "Owner", ["jane"])
    assert person_filter_matches(page, "Owner", ["example.com"])
    assert not person_filter_matches(page, "Owner", ["missing"])


def test_keyword_matches_requires_all_comma_separated_terms_across_title_properties_and_body():
    page = make_page()

    assert keyword_matches(page, "The body contains markdown export details", "quarterly, markdown")
    assert not keyword_matches(page, "The body contains markdown export details", "quarterly, absent")
