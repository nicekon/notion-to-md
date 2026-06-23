# 0001. Agent Handoff Memory

Date: 2026-06-24

## Status

Accepted

## Context

Long Codex conversations eventually consume context. Starting a new session by re-reading the whole codebase is slow and error-prone, especially when the project has hidden decisions such as:

- why it is a local Streamlit app,
- how Notion permissions affect comments and user lookup,
- how wizard state and preview state are managed,
- which files are generated and must not be committed.

The project needs a durable, checked-in memory structure that works across machines and does not depend on one chat thread.

## Decision

Use a layered documentation structure:

1. `AGENTS.md`
   - Short, automatically loaded instructions for Codex and compatible coding agents.
   - Contains setup, verification, architecture map, and hard project rules.

2. `CLAUDE.md`
   - Imports `AGENTS.md` for Claude Code compatibility.
   - Avoids duplicating instructions across agent ecosystems.

3. `docs/project-state.md`
   - Detailed current state and handoff prompt.
   - Updated when behavior, constraints, or next work changes.

4. `docs/decisions/`
   - Lightweight ADR-style records for durable decisions and tradeoffs.

## Sources Checked

- OpenAI Codex manual, `Custom instructions with AGENTS.md`: Codex discovers `AGENTS.md` files from global/project scopes and loads project instructions at session start. Source URL checked through the current Codex manual: https://developers.openai.com/codex/guides/agents-md.md
- OpenAI Codex manual, `Memories`: stable team guidance should live in `AGENTS.md` or checked-in documentation, while memories are a helpful local recall layer. Source URL checked through the current Codex manual: https://developers.openai.com/codex/memories.md
- AGENTS.md open format: `AGENTS.md` is a predictable place for coding-agent instructions and commonly includes project overview, build/test commands, style, tests, and security considerations. Source: https://agents.md/
- Claude Code memory docs: Claude Code uses `CLAUDE.md` and recommends importing `AGENTS.md` when a repo already uses it for shared agent instructions. Source: https://docs.anthropic.com/en/docs/claude-code/memory
- ADR practice: keep decisions concise and separate from implementation documentation so future maintainers can understand context and consequences. Source: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions

## Consequences

- New sessions should read `AGENTS.md` first and `docs/project-state.md` second.
- `AGENTS.md` must stay compact; detailed narrative belongs in `docs/project-state.md`.
- When implementation changes affect future handoff, update `docs/project-state.md`.
- When a durable decision changes, add or update a decision record.
- Local memories may help but are not the source of truth.
