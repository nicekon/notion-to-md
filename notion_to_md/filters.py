from __future__ import annotations

from datetime import date
from typing import Any

from .exporter import page_title, property_to_text


def build_api_filter(
    *,
    date_property: str | None = None,
    date_property_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    option_property: str | None = None,
    option_property_type: str | None = None,
    option_value: str | None = None,
) -> dict[str, Any] | None:
    filters: list[dict[str, Any]] = []

    date_filter_key = date_property_type if date_property_type in {"created_time", "last_edited_time"} else "date"
    if date_property and start_date:
        filters.append({"property": date_property, date_filter_key: {"on_or_after": start_date.isoformat()}})
    if date_property and end_date:
        filters.append({"property": date_property, date_filter_key: {"on_or_before": end_date.isoformat()}})

    if option_property and option_property_type and option_value:
        option_value = option_value.strip()
        if option_property_type == "status":
            filters.append({"property": option_property, "status": {"equals": option_value}})
        elif option_property_type == "select":
            filters.append({"property": option_property, "select": {"equals": option_value}})
        elif option_property_type == "multi_select":
            filters.append({"property": option_property, "multi_select": {"contains": option_value}})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"and": filters}


def comma_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def property_schema_by_type(schema: dict[str, Any], prop_types: set[str]) -> list[str]:
    return [name for name, prop in schema.items() if prop.get("type") in prop_types]


def option_values(prop_schema: dict[str, Any]) -> list[str]:
    prop_type = prop_schema.get("type")
    data = prop_schema.get(prop_type) or {}
    options = data.get("options") or []
    return [item.get("name", "") for item in options if item.get("name")]


def person_filter_matches(page: dict[str, Any], person_property: str | None, terms: list[str]) -> bool:
    if not terms:
        return True
    if not person_property:
        return True

    value = page.get("properties", {}).get(person_property)
    if not value:
        return False
    rendered = property_to_text(value).lower()
    return any(term in rendered for term in terms)


def keyword_matches(page: dict[str, Any], body_markdown: str, keyword: str | None) -> bool:
    if not keyword or not keyword.strip():
        return True

    terms = comma_terms(keyword)
    properties_text = "\n".join(property_to_text(value) for value in page.get("properties", {}).values())
    haystack = "\n".join([page_title(page), properties_text, body_markdown]).lower()
    return all(term in haystack for term in terms)
