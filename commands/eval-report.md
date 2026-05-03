---
name: eval-report
description: Generate an HTML report from MCP eval results and grading data.
arguments:
  - name: workspace
    description: Path to the eval-workspace directory (default: eval-workspace)
    required: false
---

# /eval-report

Generate a self-contained HTML dashboard from eval results.

## Steps

1. **Check prerequisites** — Verify the workspace has `run_summary.json` and at least some `grading.json` files. If grading hasn't been run, suggest `/eval-grade` first. The report can still generate without grading data, but assertion results will be empty.

2. **Generate report** — Run the report generator:
   ```bash
   python3 scripts/report.py <workspace>
   ```
   Output: `<workspace>/eval-report.html`

3. **Open the report** — Open the HTML file in the default browser:
   ```bash
   open <workspace>/eval-report.html
   ```

4. **Walk the user through it** — The report contains:
   - **Server overview**: name, URL, test count, timestamp
   - **Summary stats**: pass/fail/error counts, total tokens, total bytes
   - **Per-tool cards**: each test with status badge, timing, token cost, and assertion pass/fail
   - **Token cost analysis**: tools ranked by estimated token consumption
   - **Embed comparison**: side-by-side token costs for tools tested with different embed params

   The key question the report answers: "Which tools are production-ready, which need fixes, and which are too expensive?"

## Output

`<workspace>/eval-report.html` — self-contained, no external dependencies. Can be shared as a standalone file.
