# AGENTS.md

## Project Purpose

This repo contains a local Streamlit app that exports Notion database/data source pages to Markdown, including page body content, comments, export summaries, and ZIP downloads.

Use this file as the fast startup context for coding agents. For detailed current state and handoff notes, read `docs/project-state.md`.

## Setup

- Create a virtual environment: `python3 -m venv .venv`
- Activate it: `source .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Create local secrets: `cp .env.example .env`
- Put `NOTION_TOKEN` in `.env`. Never commit `.env`, exported Markdown, or generated cache files.
- Run the app: `streamlit run app.py`

## Verification

- Always run `python3 -m py_compile app.py notion_to_md/*.py` after Python edits.
- For UI changes, check `http://localhost:8501/` in the in-app browser when feasible.
- For Notion API behavior, prefer small manual checks because live API results depend on the user's integration permissions and DB access.

## Architecture Map

- `app.py`: Streamlit UI, wizard flow, preview/export orchestration, presets.
- `notion_to_md/notion_client.py`: Notion API wrapper for data sources, pages, comments, users, and Markdown.
- `notion_to_md/filters.py`: API filter construction and local filters.
- `notion_to_md/exporter.py`: Markdown rendering, filenames, summaries, ZIP creation.
- `notion_to_md/utils.py`: Notion ID parsing and timestamp helpers.
- `README.md`: user-facing setup and usage.
- `docs/project-state.md`: current implementation state, handoff prompt, known constraints, next work.
- `docs/decisions/`: lightweight ADR-style decision records.

## Implementation Rules

- Keep the app local-first. Do not introduce a hosted backend unless the user explicitly asks.
- Preserve Streamlit as the UI framework unless there is a clear user-approved reason to migrate.
- Keep Notion tokens in `.env` or user input only. Do not save tokens in presets, summaries, logs, or docs.
- Keep generated outputs under `exports/`; they are ignored by git.
- Prefer Notion API structured objects over ad hoc parsing.
- When changing search or export behavior, update `docs/project-state.md` if the new behavior affects future handoff.
- If adding durable architectural choices, add or update a short file under `docs/decisions/`.

## Current Workflow

The app uses a three-step wizard:

1. `연결`: load Notion DB/data source schema.
2. `검색`: set filters and run preview.
3. `내보내기`: choose pages and Markdown options, then save/download.

The export step should only use preview results that match the current search config.

## Git

- Main remote: `git@github.com:nicekon/notion-to-md.git`
- Default branch: `main`
- Commit generated documentation changes when they are part of the requested work.
