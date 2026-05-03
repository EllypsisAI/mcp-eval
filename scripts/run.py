#!/usr/bin/env python3
"""MCP server eval runner (HTTP mode).

Reads test cases from an eval JSON file, calls each tool over MCP Streamable
HTTP transport, captures raw responses with metrics. Use this when the MCP
server you're evaluating exposes an HTTP endpoint. For OAuth-only or
in-process MCPs (claude.ai integrations, stdio servers), use /eval-capture
instead.

Usage:
    python3 scripts/run.py <eval-tests.json> [--output-dir <dir>]

Produces per-test:
    <output-dir>/<test-name>/response.json   raw MCP tool response
    <output-dir>/<test-name>/timing.json     tokens, bytes, duration, fields
    <output-dir>/<test-name>/meta.json       test definition + tool schema
    <output-dir>/run_summary.json            aggregate results
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _metrics import compute_timing, detect_mcp_error  # noqa: E402


def mcp_request(url, session_id, method, params=None, req_id=1):
    """Send a JSON-RPC request to the MCP server. Returns (parsed, raw, session_id)."""
    body = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params:
        body["params"] = params

    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    resp = urllib.request.urlopen(req)
    raw = resp.read().decode()
    resp_headers = dict(resp.headers)
    new_session = resp_headers.get(
        "mcp-session-id", resp_headers.get("Mcp-Session-Id", session_id)
    )

    parsed = None
    for line in raw.split("\n"):
        if line.startswith("data:"):
            parsed = json.loads(line[5:].strip())
            break

    if parsed is None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}

    return parsed, raw, new_session


def initialize(url):
    """MCP handshake. Returns (session_id, init_response)."""
    params = {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "mcp-eval-runner", "version": "0.2.0"},
    }
    parsed, _, session_id = mcp_request(url, None, "initialize", params, req_id=0)

    notify_body = json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(url, data=notify_body, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass

    return session_id, parsed


def get_tool_descriptions(url, session_id):
    """Fetch all tool definitions from the server."""
    parsed, _, session_id = mcp_request(url, session_id, "tools/list", req_id=1)
    tools = parsed.get("result", {}).get("tools", [])
    return {t["name"]: t for t in tools}, session_id


def call_tool(url, session_id, tool_name, arguments, req_id=10):
    """Call a tool. Returns (result_dict_with_metrics, raw_text, session_id)."""
    start = time.time()
    parsed, raw, session_id = mcp_request(
        url, session_id, "tools/call",
        {"name": tool_name, "arguments": arguments},
        req_id=req_id,
    )
    duration_ms = round((time.time() - start) * 1000, 1)
    result = parsed.get("result", parsed)
    return result, raw, duration_ms, session_id


def run_eval(eval_file, output_dir):
    """Run all tests in an eval-tests.json file."""
    with open(eval_file) as f:
        eval_data = json.load(f)

    url = eval_data["url"]
    os.makedirs(output_dir, exist_ok=True)

    print(f"Connecting to {eval_data['server']}...")
    session_id, _ = initialize(url)
    print(f"Session: {session_id}\n")

    tool_defs, session_id = get_tool_descriptions(url, session_id)
    print(f"Server has {len(tool_defs)} tools\n")

    tests = eval_data["tests"]
    results_summary = []

    for i, test in enumerate(tests):
        test_name = test["name"]
        tool_name = test["tool"]
        params = test.get("params", {})

        has_unfilled = any(
            isinstance(v, str) and v.startswith("FILL_FROM_") for v in params.values()
        )
        if has_unfilled:
            print(f"[{test['id']}] {test_name} - SKIPPED (unfilled dependency)")
            results_summary.append({
                "id": test["id"],
                "name": test_name,
                "status": "skipped",
                "reason": "unfilled dependency param",
            })
            continue

        print(f"[{test['id']}] {test_name} - calling {tool_name}...")

        try:
            result, raw, duration_ms, session_id = call_tool(
                url, session_id, tool_name, params, req_id=10 + i
            )
            is_error, err_msg = detect_mcp_error(result)
            status = "mcp_error" if is_error else "success"
            error = err_msg if is_error else None
            if is_error:
                print(f"  MCP ERROR: {err_msg}")
        except Exception as e:
            result = None
            raw = ""
            duration_ms = None
            status = "error"
            error = str(e)
            print(f"  HTTP ERROR: {error}")

        test_dir = os.path.join(output_dir, test_name)
        os.makedirs(test_dir, exist_ok=True)

        if result is not None:
            with open(os.path.join(test_dir, "response.json"), "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            with open(os.path.join(test_dir, "raw_response.txt"), "w") as f:
                f.write(raw)

            timing = compute_timing(result, raw_text=raw, duration_ms=duration_ms)
            with open(os.path.join(test_dir, "timing.json"), "w") as f:
                json.dump(timing, f, indent=2)

            print(
                f"  {timing['duration_ms']}ms | {timing['response_bytes']}B | "
                f"~{timing['estimated_tokens']} tokens | {timing['field_count']} fields"
            )
        else:
            with open(os.path.join(test_dir, "timing.json"), "w") as f:
                json.dump({"error": error}, f, indent=2)
            timing = {"response_bytes": None, "estimated_tokens": None}

        meta = {
            "test": test,
            "tool_definition": tool_defs.get(tool_name, {}),
        }
        with open(os.path.join(test_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        results_summary.append({
            "id": test["id"],
            "name": test_name,
            "tool": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "response_bytes": timing.get("response_bytes"),
            "estimated_tokens": timing.get("estimated_tokens"),
            "error": error,
        })

    summary = {
        "server": eval_data["server"],
        "url": eval_data["url"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "http",
        "tests_total": len(tests),
        "tests_run": sum(1 for r in results_summary if r["status"] == "success"),
        "tests_skipped": sum(1 for r in results_summary if r["status"] == "skipped"),
        "tests_error": sum(1 for r in results_summary if r["status"] in ("error", "mcp_error")),
        "total_bytes": sum(r.get("response_bytes", 0) or 0 for r in results_summary),
        "total_estimated_tokens": sum(r.get("estimated_tokens", 0) or 0 for r in results_summary),
        "results": results_summary,
    }
    with open(os.path.join(output_dir, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print()
    print(f"Done. {summary['tests_run']}/{summary['tests_total']} tests run.")
    print(f"Total: {summary['total_bytes']}B | ~{summary['total_estimated_tokens']} tokens")
    print(f"Results in: {output_dir}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run.py <eval-tests.json> [--output-dir <dir>]")
        sys.exit(1)

    eval_file = sys.argv[1]
    output_dir = "eval-workspace"

    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            output_dir = sys.argv[idx + 1]

    run_eval(eval_file, output_dir)
