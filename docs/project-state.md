# Project State

Last updated: 2026-06-24

## Purpose

Build a local Python web app that accepts a Notion DB URL or data source ID, searches pages by conditions such as date/person/status/keyword, retrieves page Markdown and comments, and saves selected pages as Markdown files.

The user wants this project to be easy to resume from a new Codex session without re-reading the entire codebase. Start new sessions by reading `AGENTS.md`, then this file.

## Repository

- GitHub: `git@github.com:nicekon/notion-to-md.git`
- Branch: `main`
- Initial pushed commit: `2a872a2 Initial Notion export app`
- Local app URL while running: `http://localhost:8501/`

## Current Stack

- Python 3
- Streamlit for local web UI
- `requests` for Notion API calls
- `python-dotenv` for `.env`
- No hosted backend
- No database other than local `presets.json`

## Current User-Facing Flow

The UI is a three-step wizard.

1. `연결`
   - User enters Notion DB URL or data source ID.
   - App loads database/data source schema.
   - User selects a data source if the DB has multiple sources.

2. `검색`
   - User selects date/person/status properties.
   - Date modes: `전체`, `시작일 이후`, `종료일 이전`, `기간`.
   - In `기간`, if only the start date is entered, the end date is treated as the same date.
   - User can filter by person name/email, status/select/multi-select value, keyword, max page count.
   - User can include body preview.
   - `미리 조회` stores preview results and the exact search config.
   - `다음: 내보내기` is enabled only when the current search controls match the preview config.

3. `내보내기`
   - User sees preview counts, warnings, issues, and expected filenames.
   - User selects pages in a table.
   - User selects filename style and Markdown options.
   - User can choose comments-only output, which skips body Markdown and Properties.
   - User can include/exclude YAML frontmatter, properties table, source URL, comments section.
   - User can save only pages that have comments or export comments only.
   - User chooses comment scope: page comments only, or page + descendant block comments.
   - App writes Markdown files, `_export_summary.md`, and offers ZIP download.

## Implemented Features

- Shows a local app version caption under the main title so the browser can be checked against the current code.
- Loads Notion DB/data source schema.
- Uses Notion data source query API.
- Supports API-side date/status/select/multi-select filters where possible.
- Applies local person filter by displayed name/email.
- Applies local keyword search across title/properties/body.
- Fetches page body Markdown through Notion API.
- Fetches page comments.
- Optionally fetches comments on descendant body blocks.
- Hydrates comment authors through Notion user lookup when `created_by` does not include a display name.
- Caches page body Markdown during a session.
- Caches Notion user lookup results during a session.
- Falls back to user ID if Notion user information capability is missing.
- Generates Markdown frontmatter and properties table.
- Supports comments-only Markdown output that skips page body retrieval and omits Body/Properties sections.
- Omits empty comments section when configured.
- Supports "댓글 있는 페이지만 저장".
- Shows pages skipped by the comment-presence filter in the UI and export summary.
- Records partial failures and warnings in UI and export summary.
- Creates `_export_summary.md` for each export batch.
- Prevents duplicate filenames by appending suffixes.
- Provides filename styles based on title, page ID, date, status, and person.
- Saves presets in `presets.json` without tokens.
- Keeps secrets and exports out of git.
- Displays the running app version near the title and in a small footer for deployment/restart confirmation.
- Focused pytest coverage exists for filename generation and filter helpers.

## Important Files

- `app.py`
  - Main Streamlit app.
  - Defines `APP_VERSION` and renders visible version captions near the title and footer.
  - Contains wizard state in `st.session_state["wizard_step"]`.
  - Contains preview state such as `preview_pages`, `preview_rows`, `preview_config`.
  - Contains export state such as `export_results`, `export_files`, `export_issues`.

- `notion_to_md/notion_client.py`
  - Wraps Notion API requests.
  - Handles data source listing/retrieval, querying, Markdown retrieval, comments, descendant blocks, and user lookup.

- `notion_to_md/exporter.py`
  - Renders Markdown files.
  - Builds safe filenames.
  - Creates ZIP bytes.
  - Writes `_export_summary.md`.

- `notion_to_md/filters.py`
  - Builds Notion query filters.
  - Handles local person, keyword, and option matching.

- `README.md`
  - Human-facing setup and usage.

## Known Constraints

- `.env` is required on each machine and is not committed.
- Notion integration must be invited to the target DB.
- Comment and user-name lookup depend on Notion integration capabilities.
- Body keyword search is slower because it fetches page Markdown before filtering.
- Descendant block comment search can be slow on large pages.
- The app is intended for local use; no authentication layer exists beyond the local Notion token.
- Streamlit reruns the script on interactions, so persistent state must live in `st.session_state` or local files.

## Verification Commands

```bash
python3 -m py_compile app.py notion_to_md/*.py
python3 -m pytest tests
streamlit run app.py
```

For UI verification, open `http://localhost:8501/` and check the wizard:

- Confirm the title area shows `실행 중인 버전: v2026.06.24-comments-only` after restarting the server.
- Step 1 should not show search/export controls.
- Step 2 should not enable `다음: 내보내기` until preview matches current filters.
- Step 3 should allow returning to search with `이전`.

## Latest Documentation Method Applied

The repo now uses a compact agent handoff pattern:

- `AGENTS.md` for automatically loaded, durable coding-agent instructions.
- `CLAUDE.md` importing `AGENTS.md` for Claude Code compatibility.
- `docs/project-state.md` for detailed, manually maintained current state.
- `docs/decisions/` for ADR-style decision records.

Rationale:

- Keep always-loaded context short.
- Keep rich handoff context available on demand.
- Avoid relying on one chat thread, hidden memory, or machine-local `.env`.
- Record decisions separately from implementation details so future agents can understand why the app is shaped this way.

## Handoff Prompt For A New Session

Use this when starting a fresh Codex session on another machine:

```text
This repo is a local Streamlit app that exports Notion DB/data source pages to Markdown.
Please read AGENTS.md and docs/project-state.md first, then continue from the current branch.

Important constraints:
- Keep it local-first and Python/Streamlit based.
- Never commit .env, tokens, exports, presets, or generated cache files.
- Run python3 -m py_compile app.py notion_to_md/*.py after Python edits.
- Run python3 -m pytest tests after testable logic changes.
- The current UI is a three-step wizard: 연결 > 검색 > 내보내기.
- Confirm the visible app version after restart: `실행 중인 버전: v2026.06.24-comments-only`.
```

## Good Next Work

- Add more coverage around Streamlit wizard state and export summary rendering.
- Improve large export progress feedback and cancellation behavior.
- Add a small "connection status" summary on search/export steps.
- Add optional export path chooser or per-run folder naming.
- Add a troubleshooting panel for Notion permission/capability failures.
