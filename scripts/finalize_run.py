#!/usr/bin/env python3
"""Build run_summary.json from individual per-test directories.

Both run.py (HTTP mode) and /eval-capture (Claude mode) produce identical
per-test directory shapes. run.py writes its own run_summary.json at the
end. Claude-mode tests are captured one at a time, so this helper walks the
workspace after the fact and emits the same summary shape.

Usage:
    python3 scripts/finalize_run.py <eval-tests.json> <output-dir>
"""

import json
import os
import sys
import time


def finalize(eval_file, output_dir):
    with open(eval_file) as f:
        eval_data = json.load(f)

    results = []
    for test in eval_data.get("tests", []):
        name = test.get("name")
        test_dir = os.path.join(output_dir, name)
        timing_path = os.path.join(test_dir, "timing.json")
        response_path = os.path.join(test_dir, "response.json")

        if not os.path.exists(response_path):
            results.append({
                "id": test.get("id"),
                "name": name,
                "tool": test.get("tool"),
                "status": "skipped",
                "reason": "no response captured",
            })
            continue

        timing = {}
        if os.path.exists(timing_path):
            with open(timing_path) as f:
                timing = json.load(f)

        with open(response_path) as f:
            response = json.load(f)

        is_error = isinstance(response, dict) and response.get("isError")
        error_msg = None
        if is_error:
            content = response.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "") if isinstance(content[0], dict) else ""
                error_msg = text.split("\n")[0][:300]

        results.append({
            "id": test.get("id"),
            "name": name,
            "tool": test.get("tool"),
            "status": "mcp_error" if is_error else "success",
            "duration_ms": timing.get("duration_ms"),
            "response_bytes": timing.get("response_bytes"),
            "estimated_tokens": timing.get("estimated_tokens"),
            "error": error_msg,
        })

    summary = {
        "server": eval_data.get("server"),
        "url": eval_data.get("url"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": eval_data.get("mode", "capture"),
        "tests_total": len(results),
        "tests_run": sum(1 for r in results if r["status"] == "success"),
        "tests_skipped": sum(1 for r in results if r["status"] == "skipped"),
        "tests_error": sum(1 for r in results if r["status"] in ("error", "mcp_error")),
        "total_bytes": sum(r.get("response_bytes", 0) or 0 for r in results),
        "total_estimated_tokens": sum(r.get("estimated_tokens", 0) or 0 for r in results),
        "results": results,
    }

    summary_path = os.path.join(output_dir, "run_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Summary written: {summary_path}")
    print(f"  {summary['tests_run']}/{summary['tests_total']} success, "
          f"{summary['tests_error']} error, {summary['tests_skipped']} skipped")
    print(f"  ~{summary['total_estimated_tokens']} tokens total")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/finalize_run.py <eval-tests.json> <output-dir>")
        sys.exit(1)
    finalize(sys.argv[1], sys.argv[2])
