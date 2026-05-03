# Changelog

This is design documentation, not release notes. Each entry captures what changed and *why* — including the failure modes of prior versions.

## [0.2.0] — 2026-05-03

### What changed

Cleaned up for public release. The plugin now ships as its own repo, generic across any MCP server, with tests and a public-ready README/LICENSE.

### Why

v0.1.0 was usable but had three defects that blocked shipping:

1. **Server-specific code embedded in scripts.** `scripts/grade.py`'s field-name normalization carried a Capsule-CRM-shaped vocabulary (`pipelines`, `milestones`, `stages`, `tracks`). It didn't break for other servers, but it announced "this was built for Capsule" to anyone reading the source. The plugin grades the *output* of any MCP server's tools — that means generic transforms only. Anything CRM-specific (or x-research-specific, or analytics-specific) would belong in the assertion text, where the LLM grader handles it.

2. **One-shot scripts at the repo root with hardcoded PII.** `build-workspace.py` and `llm-grade-patch.py` were workarounds for evaluating claude.ai OAuth integrations (Gmail, Calendar) that don't expose HTTP endpoints. They worked once, then rotted — they had a typo'd absolute path and embedded the developer's email, contacts, and draft subjects. Deleted.

3. **No way to evaluate non-HTTP MCPs.** Solved properly this release.

### Design changes

| Before | After | Why |
|---|---|---|
| `/eval-run` only (HTTP runner) | `/eval-run` (HTTP) + `/eval-capture` (Claude-mode) | Server transports vary. HTTP suits servers Claude evaluates from outside; Claude-mode handles OAuth, stdio, and any in-conversation MCP. Both paths produce identical workspace shapes so `/eval-grade` and `/eval-report` stay mode-agnostic. |
| Inline metric/parsing logic in `run.py` | `scripts/_metrics.py` shared by `run.py` + `capture.py` | Two runners, one source of truth. Token counts and field-walks won't drift. |
| `templates/capsule-example.json` | `examples/capsule-crm.json` + `examples/x-research-stdio.json` | A "template" you'd start from is different from a worked example. Two examples (HTTP + stdio) show both transport modes. |
| 25-entry server-specific mappings dict in grade.py | Generic word-splitting + camelCase/snake_case only | Tests now pin this contract. Server-specific terminology pushes to LLM grading where it belongs. |
| No tests | 76 tests covering grading, metrics, capture, and full pipeline | Grading regex was the riskiest piece — uncovered code that turned "each item has X" universal claims into existential ones. Fixed. |

### New components

- `commands/eval-capture.md` — Claude-driven runner for OAuth-only and stdio MCPs.
- `scripts/capture.py` — bookkeeping helper Claude calls per test in capture mode.
- `scripts/finalize_run.py` — builds `run_summary.json` after Claude-mode captures.
- `scripts/_metrics.py` — shared timing/parsing module.
- `tests/` — pytest suite (`test_metrics.py`, `test_grade.py`, `test_capture.py`, `test_pipeline.py`).
- `examples/x-research-stdio.json` — second worked example covering stdio transport.
- `.gitignore`, `LICENSE` (MIT), `README.md`.

### Bug fixes

- `check_each_has_field` previously satisfied "each result has X" if X was found nested in *any one* item. Now it requires every item to have the field somewhere in its tree. Caught by `tests/test_grade.py`.

## [0.1.0] — 2026-03-07

### What changed

Initial implementation: four-stage pipeline (init → run → grade → report) targeting Streamable HTTP MCP servers.

### Why this design

MCP servers sit between Claude and live business systems. A tool returning 50k tokens of HTML when the workflow needed 200 tokens of structured data silently degrades downstream skills. A tool dropping fields makes downstream workflows fail in ways that are hard to trace. The eval catches those problems before they reach production — and grades server *output*, not server code, so it works for any MCP regardless of implementation language.

### Components

- `scripts/run.py` — Streamable HTTP runner with the MCP `initialize` + `notifications/initialized` handshake.
- `scripts/grade.py` — programmatic checker with regex-based assertion matchers.
- `scripts/report.py` — self-contained dark-mode HTML dashboard.
- `agents/grader.md` — LLM grader for assertions that need semantic judgment.
- `skills/evaluate/SKILL.md` — pipeline overview.
- `commands/eval-{init,run,grade,report}.md` — pipeline stages.

### Validated against

Capsule CRM (n8n-hosted), Apollo, Perplexity, Analytics Toolbox, X Research, productivity stack (Gmail/Calendar — via the deprecated one-shot capture path). The productivity-stack experience is what motivated v0.2's `/eval-capture`.
