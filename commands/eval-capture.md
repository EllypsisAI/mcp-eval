---
description: Run an MCP eval against a server Claude can already see (OAuth, stdio, in-conversation MCPs that don't expose an HTTP endpoint).
argument-hint: "[test-file] [output-dir]"
---

# /eval-capture

Run an eval against an MCP server that doesn't expose a Streamable HTTP endpoint — claude.ai OAuth integrations (Gmail, Google Calendar, Slack, etc.), stdio servers configured in Claude Code, anything where the tools are available *to you* but a subprocess can't reach them.

The output is identical to `/eval-run` — same per-test directory shape, same `run_summary.json`. `/eval-grade` and `/eval-report` work without modification.

## When to use this instead of `/eval-run`

| Server type | Command |
|-------------|---------|
| HTTP/Streamable HTTP (n8n, custom servers, Smithery) | `/eval-run` |
| claude.ai OAuth integration (Gmail, GCal, Slack, Drive, etc.) | `/eval-capture` |
| stdio MCP configured in `.mcp.json` | `/eval-capture` |
| Anything Claude can call as `mcp__server-name__tool` | `/eval-capture` |

## Steps

1. **Load the test file.** Read `<test-file>` (default `eval-tests.json`). For each test, you'll need: `name`, `tool`, `params`, `id`.

2. **Verify the tools are available.** The MCP tools must already be loaded in this conversation. If a test references a tool you can't see, fail fast — tell the user which tool is missing and how to connect it.

3. **For each test, in order:**

   - If `params` contains a `FILL_FROM_<id>.<path>` value that hasn't been resolved (the dependency hasn't run yet, or its response didn't have that path), call `scripts/capture.py` with `--status skipped --reason "unfilled dependency"` and move on.

   - Call the MCP tool directly. The tool name in the test file should match the server-side name. In Claude Code, MCP tools are surfaced as `mcp__<server>__<tool>` — strip the prefix when matching.

   - Take the tool's JSON response and pipe it to `scripts/capture.py`:

     ```bash
     python3 scripts/capture.py <test-file> <test-name> <output-dir> --response-file /tmp/eval-resp.json
     ```

     Or pipe via stdin if you'd rather not write a temp file:
     ```bash
     echo '<json>' | python3 scripts/capture.py <test-file> <test-name> <output-dir>
     ```

   - If a `FILL_FROM_` value resolves from the response of an earlier test, substitute it in memory before calling the tool. The capture script doesn't help with this — Claude does it.

4. **Finalize the summary.** After all tests, run:
   ```bash
   python3 scripts/finalize_run.py <test-file> <output-dir>
   ```
   This writes `run_summary.json` in the same shape `/eval-run` produces.

5. **Report.** Show the user:

   | Metric | Value |
   |--------|-------|
   | Tests run | X / Y |
   | Skipped | Z (unfilled deps) |
   | Errors | N |
   | Total bytes | X KB |
   | Est. tokens | ~X |

   Then: "Run `/eval-grade <output-dir>` to score the responses."

## Notes

- **Duration**: Claude-mode can't measure tool latency the way the HTTP runner can. `duration_ms` will be `null` in `timing.json`. Token cost and field count still work — those are the metrics that matter for production-readiness anyway.
- **Tool definitions**: If the connected MCP server doesn't expose schemas to you, `meta.json`'s `tool_definition` will be a minimal stub. The grader still works; the report just shows less in the "tool catalog" section.
- **Errors**: If the tool throws an exception or returns an `isError: true` payload, capture it anyway — error responses are signal. The grader will fail data-presence assertions automatically against errors.

## Output

```
<output-dir>/
  run_summary.json
  <test-name>/
    response.json
    timing.json
    meta.json
```
