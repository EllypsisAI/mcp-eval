---
name: eval-init
description: Connect to an MCP server and scaffold test cases for every tool it exposes.
arguments:
  - name: url
    description: MCP server endpoint URL, OR "claude" / "stdio" for in-conversation MCPs
    required: true
  - name: output
    description: Output file path (default: eval-tests.json)
    required: false
---

# /eval-init

Scaffold a complete test file for an MCP server. Works in two modes depending on what's reachable.

## Mode A — HTTP server

When `<url>` is `https://...` or `http://...`:

1. **Connect** — Initialize an MCP session at the URL using the same handshake as `scripts/run.py`: send `initialize` with protocol version `2025-03-26`, then `notifications/initialized`.
2. **Discover tools** — Call `tools/list` to get every tool's name, description, and input schema.
3. **Continue with step 3 below.**

## Mode B — Claude-mode (OAuth or stdio MCPs)

When the user passes `claude`, `stdio`, or omits a real URL because the server is already connected to *this* Claude conversation:

1. **Inventory the connected tools** — Look at what `mcp__<server>__<tool>` tools are available. Group them by server.
2. **If multiple servers are connected**, ask the user which one to evaluate.
3. **Continue with step 3 below**, using the in-conversation tool schemas as your source of truth. The test file's `url` should be set to `stdio://...` or `claude://<server-name>` so `/eval-run` knows to redirect to `/eval-capture`.

## Step 3 — Scaffold tests (both modes)

For each tool, create a test case entry:
- `id`: kebab-case from tool name (e.g., `search-contacts-1`)
- `name`: descriptive slug (e.g., `search-known-company`)
- `tool`: exact tool name as the server exposes it (without any `mcp__server__` prefix Claude Code adds)
- `params`: one key per required param, with a suggested value based on the schema type. Use `"FILL_FROM_<test-id>.<json.path>"` for params that depend on another test's output.
- `workflow_step`: brief description of what this test validates
- `assertions`: 2-3 starter assertions based on the tool description and return schema

## Step 4 — Write the file

Save as JSON matching the schema in `references/test-schema.md`. Include the `server`, `url`, `timestamp`, and `context` fields.

## Step 5 — Present summary

Show the user a table of scaffolded tests and flag:
- Params that need real values (IDs, specific queries)
- Tools with no required params (may work as-is)
- Suggested `depends_on` chains

Tell the user: "Review the test file and fill in realistic param values. The scaffolder guessed defaults from the schema, but real IDs and queries will produce a meaningful eval."

Then point them at the right runner:
- HTTP server → `/eval-run`
- Claude-mode → `/eval-capture`

## Output

`eval-tests.json` (or custom path) — ready for the runner after user review.
