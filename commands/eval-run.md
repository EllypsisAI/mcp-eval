---
description: Execute MCP eval test cases against a live server (HTTP transport) and capture responses.
argument-hint: "[test-file] [output-dir]"
---

# /eval-run

Run all test cases against an MCP server over HTTP and capture raw results.

## When to use this vs `/eval-capture`

- This command (`/eval-run`) hits the server directly via Streamable HTTP from a subprocess. Use it for n8n-hosted servers, custom HTTP MCPs, Smithery deployments — anything with an `https://...` URL.
- For OAuth integrations or stdio MCPs that Claude can already see but a subprocess can't reach, use `/eval-capture` instead.

If the test file's `url` field starts with `stdio://`, `claude://`, or doesn't look like an HTTP URL, redirect the user to `/eval-capture`.

## Steps

1. **Validate** — Check that the test file exists and is valid JSON. Confirm the `url` is HTTP/HTTPS. Warn if any tests have `FILL_FROM_` params that haven't been resolved (they'll be skipped).

2. **Execute**:
   ```bash
   python3 scripts/run.py <test-file> --output-dir <output-dir>
   ```

3. **Report summary** — After the run completes, read `<output-dir>/run_summary.json` and present:

   | Metric | Value |
   |--------|-------|
   | Tests run | X / Y |
   | Skipped | Z (unfilled deps) |
   | Errors | N |
   | Total bytes | X KB |
   | Est. tokens | ~X |

   If there are errors, show which tests failed and the error messages.

4. **Next step** — Tell the user: "Run `/eval-grade` to score the responses, or review the raw outputs in `<output-dir>/`."

## Output

```
<output-dir>/
  run_summary.json          aggregate results
  <test-name>/
    response.json           raw MCP tool response
    raw_response.txt        full SSE response as received
    timing.json             duration, bytes, tokens, field count
    meta.json               test definition + tool schema
```
