# mcp-eval

A Claude Code plugin that evaluates MCP servers for production readiness. Test every tool a server exposes, measure token costs, grade the responses against your assertions, and generate a visual report you can share with your team.

The plugin grades the **output** of an MCP server's tools — does each tool return useful, structured, affordable data — not the server's source code. That makes it server-agnostic. It works for any MCP server: HTTP, stdio, OAuth integrations, claude.ai connectors.

```
┌─ /eval-init  ─────► eval-tests.json     # one test per tool, scaffolded from the schema
│
├─ /eval-run   ─────► eval-workspace/     # HTTP transport
│  /eval-capture                          # OAuth / stdio / in-conversation MCPs
│
├─ /eval-grade ─────► grading.json        # pass/fail per assertion (programmatic + LLM)
│
└─ /eval-report ────► eval-report.html    # self-contained dark-mode dashboard
```

## Why this exists

MCP servers sit between Claude and live business systems. A tool that returns 50k tokens of HTML when the workflow needed 200 tokens of structured data will silently degrade every skill that depends on it. A tool that drops required fields will make downstream workflows fail in ways that are hard to trace. mcp-eval catches both classes of problem before they reach production.

It also gives you something concrete to point at when deciding whether to ship an integration: a per-tool report card with token budget, latency, error rate, and assertion pass-rate.

## Install

The plugin distributes itself as a Claude Code marketplace, so installation is two slash commands:

```
/plugin marketplace add EllypsisAI/mcp-eval
/plugin install mcp-eval@mcp-eval
```

That's it. The five commands (`/eval-init`, `/eval-run`, `/eval-capture`, `/eval-grade`, `/eval-report`), the `evaluate` skill, and the `grader` agent become available immediately.

The pipeline scripts use only the Python standard library — no `pip install` needed at runtime. The test suite needs `pytest` if you want to run it.

### Manual install (without the marketplace mechanism)

```bash
git clone https://github.com/EllypsisAI/mcp-eval.git ~/.claude/plugins/mcp-eval
```

Restart Claude Code.

## Quick start

Five-minute path from "I have an MCP server I'm thinking about using" to "I have a report I can show my team."

```
1. /eval-init https://your-mcp-server.example.com/mcp
   - Connects, lists tools, scaffolds eval-tests.json with one test per tool.

2. Open eval-tests.json. Replace placeholder param values with realistic ones
   (real IDs, real queries). Add or sharpen assertions per test.

3. /eval-run                            # HTTP servers
   /eval-capture                        # OAuth / stdio / in-Claude MCPs
   - Calls every tool, captures responses, writes timing + metadata.

4. /eval-grade
   - Programmatic checks first, LLM grader for anything semantic.

5. /eval-report
   - Generates eval-workspace/eval-report.html. Opens in your browser.
```

## The two run modes

| Server transport | Command | Why |
|---|---|---|
| Streamable HTTP (n8n, Smithery, custom) | `/eval-run` | Subprocess opens the MCP session directly. Measures real wall-clock latency. |
| OAuth integration (claude.ai Gmail, GCal, Slack, Drive...) | `/eval-capture` | OAuth tokens live in Claude's process, not yours. Claude calls each tool in-conversation, hands the response to a helper that does the bookkeeping. |
| stdio MCP (configured in `.mcp.json`) | `/eval-capture` | Same reason — the server is bound to Claude's process. |
| Anything you see as `mcp__server__tool` | `/eval-capture` | If Claude can call it, capture mode can eval it. |

Both modes produce **identical** workspace shapes. `/eval-grade` and `/eval-report` don't know or care which mode produced the data.

## What an eval test looks like

```json
{
  "id": "search-1",
  "name": "search-known-company",
  "tool": "search_contacts",
  "params": {"q": "Acme", "page": "1", "perPage": "10"},
  "workflow_step": "Verify the tool finds a known org and returns enough fields to act on",
  "assertions": [
    "Returns at least one result",
    "Each result has an ID field usable for follow-up calls",
    "Contact type (person vs organisation) is distinguishable",
    "Response includes or links to tags"
  ]
}
```

Assertions are plain English. The grader handles them in two passes:

- **Programmatic** — regex-matched patterns like *"Returns at least one result"*, *"Each result has X"*, *"X present"*, *"Returns N or fewer"*. Fast and deterministic.
- **LLM** — anything semantic ("response is useful for sales research", "results are relevant to the query") is deferred to the grader agent.

See [`references/test-schema.md`](references/test-schema.md) for the full schema and assertion patterns the programmatic grader recognizes. See [`references/grading.md`](references/grading.md) for how grading routes to programmatic vs LLM paths.

## Worked examples

| File | Server | Why it's a good example |
|---|---|---|
| [`examples/capsule-crm.json`](examples/capsule-crm.json) | Capsule CRM via n8n (HTTP) | Shows `depends_on` chains, embed-comparison test pairs, and a "context bomb" test that surfaces token bloat on high-activity contacts. |
| [`examples/x-research-stdio.json`](examples/x-research-stdio.json) | x-research (stdio MCP) | Shows the capture-mode pattern. Includes user-lookup → tweets → mentions chain via `FILL_FROM_`. |

## Repository layout

```
.
├── .claude-plugin/plugin.json    # Plugin manifest
├── agents/grader.md              # LLM grader system prompt
├── commands/                     # Slash commands (the four pipeline stages)
│   ├── eval-init.md
│   ├── eval-run.md               # HTTP runner
│   ├── eval-capture.md           # Claude-mode runner
│   ├── eval-grade.md
│   └── eval-report.md
├── examples/                     # Real worked test files
├── references/                   # Loaded by skills on demand
│   ├── grading.md
│   └── test-schema.md
├── scripts/                      # Pure-Python, stdlib only
│   ├── _metrics.py               # Shared timing/parsing helpers
│   ├── capture.py                # Claude-mode bookkeeping
│   ├── finalize_run.py           # Builds run_summary after capture
│   ├── grade.py                  # Programmatic grader
│   ├── report.py                 # HTML report generator
│   └── run.py                    # HTTP runner
├── skills/evaluate/SKILL.md      # Top-level skill that orients Claude
├── templates/eval-template.json  # Blank starting point
└── tests/                        # pytest suite (76 tests)
```

## Output anatomy

Each run produces a workspace directory. Same shape regardless of mode:

```
eval-workspace/
├── run_summary.json              # Aggregate: tests run, errors, total tokens
├── eval-report.html              # Self-contained dashboard (after /eval-report)
├── grades_summary.json           # Aggregate grading (after /eval-grade)
└── <test-name>/
    ├── response.json             # Raw tool response (MCP-wrapped)
    ├── timing.json               # Bytes, tokens, fields, duration_ms (HTTP only)
    ├── meta.json                 # Test definition + tool schema (for the grader)
    ├── grading.json              # Per-assertion verdicts + evidence (after grading)
    └── raw_response.txt          # SSE wire bytes (HTTP mode only)
```

`response.json` is the source of truth — every later stage derives from it. You can hand-edit `meta.json`'s assertions and re-run `/eval-grade` without re-hitting the server. You can hand-edit `grading.json` for assertions the grader gets wrong, then `/eval-report` to refresh the dashboard.

## Running the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest
python -m pytest tests/ -v
```

76 tests cover the metric helpers, the grading pipeline (including the regex matchers that catch *"Returns at least one result"*, *"Each result has X"*, etc.), the capture round-trip, and an end-to-end pipeline test that runs capture → grade → report on synthetic data.

## What this plugin does *not* do

- It doesn't write tests for you. It scaffolds tests from the tool schema; you make them realistic. Bad assertions produce meaningless evals.
- It doesn't auto-sample param values from production data. You fill in real IDs and queries.
- It doesn't lint, type-check, or audit the MCP server's source code. It tests the *output* — the contract the server exposes to Claude — because that's what determines whether downstream skills work.
- It doesn't measure load, concurrency, or rate-limit behavior. Single-shot per tool.
- It doesn't post results anywhere. The HTML report is the artifact; you decide where it goes.

## License

MIT. See [LICENSE](LICENSE).
