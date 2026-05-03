---
name: evaluate
description: >
  Evaluate an MCP server for production readiness. Use when the user says
  "evaluate MCP", "test MCP server", "MCP eval", "check MCP tools",
  "measure MCP", "run MCP eval", "how good is this MCP server",
  "benchmark MCP", "grade MCP tools", "audit MCP server",
  "test these tools", or wants to understand whether an MCP server's tools
  return useful data at reasonable token cost.
---

# Evaluate MCP Server

Test every tool an MCP server exposes, grade the responses, and produce a visual report showing what works, what's broken, and what costs too many tokens. The pipeline has four stages — each can run independently, but they're designed to flow in sequence.

## Why this matters

MCP servers sit between Claude and live business systems. A tool that returns 50k tokens of raw HTML when you needed 200 tokens of structured data will silently degrade every skill that depends on it. A tool that drops required fields makes downstream workflows fail in ways that are hard to trace. This eval catches those problems before they reach production.

The eval grades the **output** of an MCP server's tools — does each tool return useful, structured, affordable data — not the server's source code. That keeps the plugin server-agnostic.

## The pipeline

| Stage | Command | What it produces |
|-------|---------|-----------------|
| **Init** | `/eval-init` | `eval-tests.json` — one test per tool, pre-filled from server schema |
| **Run** (HTTP) | `/eval-run` | `eval-workspace/` — raw responses, timing, metadata per test |
| **Run** (Claude-mode) | `/eval-capture` | Same workspace shape, for OAuth or stdio MCPs |
| **Grade** | `/eval-grade` | `grading.json` per test — pass/fail on every assertion |
| **Report** | `/eval-report` | `eval-report.html` — visual dashboard of the full eval |

## Stage 1 — Init

Generate the test file. `/eval-init` connects to the server, lists tools via `tools/list`, and scaffolds a test case for each tool with params pre-filled from the schema.

After init, the user should review `eval-tests.json`:
- Fill in realistic param values (the scaffolder suggests defaults but real IDs matter)
- Add assertions that reflect what the tool *should* return for those params
- Add `depends_on` links if one test's output feeds another's params

This is the most important step. Bad test cases produce meaningless evals. Good ones catch real integration issues. Load `references/test-schema.md` for the full schema and assertion-writing guidance.

## Stage 2 — Run

Pick the right runner for the server's transport.

| If the server is... | Use |
|---|---|
| Streamable HTTP (n8n, custom servers, Smithery) | `/eval-run` |
| OAuth integration (claude.ai Gmail, Calendar, Slack, Drive) | `/eval-capture` |
| stdio MCP configured in `.mcp.json` | `/eval-capture` |
| Anything you can already see as `mcp__server__tool` | `/eval-capture` |

`/eval-run` calls `scripts/run.py`, which opens an MCP session, calls each tool, and writes per-test directories. `/eval-capture` does the same thing but Claude calls the tools (since a subprocess can't reach OAuth-or-stdio MCPs) and `scripts/capture.py` handles the bookkeeping. Both produce identical workspace shapes — every later stage is mode-agnostic.

After the run, skim `run_summary.json` to spot failures before moving to grading.

## Stage 3 — Grade

Score every response against its assertions. `/eval-grade` runs `scripts/grade.py` for programmatic checks, then defers anything ambiguous to the grader agent (from `agents/grader.md`) for LLM judgment.

Two types of assertions:

| Type | Example | How it's graded |
|------|---------|----------------|
| **Programmatic** | "Returns at least one result" | Script checks JSON structure |
| **LLM judgment** | "Response is useful for sales research" | Grader agent reads response + context |

Load `references/grading.md` for the grading schema and how to write assertions that grade cleanly.

## Stage 4 — Report

Generate the visual dashboard. `/eval-report` runs `scripts/report.py` to produce a self-contained HTML file with:

- Server overview and test summary
- Per-tool cards: status, timing, token cost, assertion results
- Token cost analysis highlighting expensive tools
- Embed comparison tables (same tool, different embed params)

Open the report in a browser to review with the user. The report is the deliverable — it answers "should we ship this MCP integration?"

## When to run partial pipelines

- **Just init**: User is designing tests for a new server, hasn't run yet
- **Run + grade + report**: Tests already exist, re-evaluating after server changes
- **Grade + report**: Re-grading with updated assertions on existing run data
- **Just report**: Re-generating the report after manual grading edits

## References

| Topic | Load |
|-------|------|
| Test case JSON schema | `references/test-schema.md` |
| Grading system | `references/grading.md` |
| Starter template | `templates/eval-template.json` |
| Real example (HTTP, CRM) | `examples/capsule-crm.json` |
| Real example (stdio, social) | `examples/x-research-stdio.json` |
