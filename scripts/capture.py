#!/usr/bin/env python3
"""Capture a single tool response into the eval workspace shape.

Used by /eval-capture for MCPs that don't expose an HTTP endpoint (claude.ai
OAuth integrations, stdio servers, anything Claude can call directly but a
subprocess can't reach). Claude calls the tool inside the conversation,
hands the JSON response to this script, and the bookkeeping (bytes, tokens,
fields, timing.json + meta.json) gets written exactly the same way run.py
writes them - so /eval-grade and /eval-report don't care which mode produced
the data.

Usage:
    python3 scripts/capture.py <eval-tests.json> <test-name> <output-dir> \
        [--response-file <path>] [--duration-ms <int>] \
        [--tool-definition <path>] [--status success|mcp_error|error] \
        [--error <message>]

If --response-file is omitted, the response JSON is read from stdin.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _metrics import compute_timing, detect_mcp_error  # noqa: E402


def load_test_definition(eval_file, test_name):
    with open(eval_file) as f:
        eval_data = json.load(f)
    for test in eval_data.get("tests", []):
        if test.get("name") == test_name:
            return test, eval_data
    raise ValueError(f"Test '{test_name}' not found in {eval_file}")


def load_response(response_file):
    if response_file:
        with open(response_file) as f:
            return json.load(f), f.name
    return json.load(sys.stdin), "<stdin>"


def write_capture(eval_file, test_name, output_dir, response,
                  duration_ms=None, tool_definition=None,
                  forced_status=None, forced_error=None):
    """Write the per-test directory + return the summary entry."""
    test, _ = load_test_definition(eval_file, test_name)
    os.makedirs(output_dir, exist_ok=True)
    test_dir = os.path.join(output_dir, test_name)
    os.makedirs(test_dir, exist_ok=True)

    is_error, err_msg = detect_mcp_error(response)
    if forced_status:
        status = forced_status
        error = forced_error
    elif is_error:
        status = "mcp_error"
        error = err_msg
    else:
        status = "success"
        error = None

    with open(os.path.join(test_dir, "response.json"), "w") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    timing = compute_timing(response, duration_ms=duration_ms)
    with open(os.path.join(test_dir, "timing.json"), "w") as f:
        json.dump(timing, f, indent=2)

    meta = {
        "test": test,
        "tool_definition": tool_definition or {
            "name": test.get("tool"),
            "description": "",
            "inputSchema": {"properties": {}, "required": list(test.get("params", {}).keys())},
        },
    }
    with open(os.path.join(test_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return {
        "id": test.get("id"),
        "name": test_name,
        "tool": test.get("tool"),
        "status": status,
        "duration_ms": duration_ms,
        "response_bytes": timing["response_bytes"],
        "estimated_tokens": timing["estimated_tokens"],
        "error": error,
    }


def write_skipped(eval_file, test_name, output_dir, reason):
    """Record a skipped test (e.g. unfilled FILL_FROM_ dependency)."""
    test, _ = load_test_definition(eval_file, test_name)
    os.makedirs(output_dir, exist_ok=True)
    return {
        "id": test.get("id"),
        "name": test_name,
        "tool": test.get("tool"),
        "status": "skipped",
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_file", help="Path to eval-tests.json")
    parser.add_argument("test_name", help="The test's `name` field (becomes the output dir)")
    parser.add_argument("output_dir", help="Workspace dir (same one /eval-grade and /eval-report read)")
    parser.add_argument("--response-file", help="Path to a JSON file with the tool response. "
                        "Omit to read from stdin.")
    parser.add_argument("--duration-ms", type=float, default=None,
                        help="Wall-clock duration of the tool call, if known.")
    parser.add_argument("--tool-definition", help="Path to JSON with the tool's schema "
                        "(name, description, inputSchema). Optional.")
    parser.add_argument("--status", choices=["success", "mcp_error", "error", "skipped"],
                        help="Override auto-detected status.")
    parser.add_argument("--error", help="Error message to record (used with --status error).")
    parser.add_argument("--reason", help="Skip reason (used with --status skipped).")
    args = parser.parse_args()

    if args.status == "skipped":
        entry = write_skipped(args.eval_file, args.test_name, args.output_dir,
                              args.reason or "skipped")
        print(json.dumps(entry, indent=2))
        return

    response, source = load_response(args.response_file)
    tool_def = None
    if args.tool_definition:
        with open(args.tool_definition) as f:
            tool_def = json.load(f)

    entry = write_capture(
        args.eval_file, args.test_name, args.output_dir,
        response,
        duration_ms=args.duration_ms,
        tool_definition=tool_def,
        forced_status=args.status,
        forced_error=args.error,
    )

    bytes_str = f"{entry['response_bytes']}B" if entry['response_bytes'] is not None else "?"
    tokens_str = f"~{entry['estimated_tokens']}" if entry['estimated_tokens'] is not None else "?"
    print(f"[{entry['status']}] {args.test_name} - {bytes_str} | {tokens_str} tokens "
          f"(captured from {source})")


if __name__ == "__main__":
    main()
