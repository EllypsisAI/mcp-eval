"""Tests for scripts/capture.py - Claude-mode workspace builder."""

import json
import os
import subprocess
import sys

import pytest

from capture import write_capture, write_skipped


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_PY = os.path.join(ROOT, "scripts", "capture.py")
FINALIZE_PY = os.path.join(ROOT, "scripts", "finalize_run.py")


@pytest.fixture
def eval_file(tmp_path):
    """A minimal eval-tests.json with two tests."""
    p = tmp_path / "eval-tests.json"
    p.write_text(json.dumps({
        "server": "Test Server",
        "url": "stdio://test",
        "timestamp": "2026-05-03",
        "context": "test fixture",
        "tests": [
            {
                "id": "t1",
                "name": "list-items",
                "tool": "list_items",
                "params": {},
                "assertions": ["Returns at least one result"],
            },
            {
                "id": "t2",
                "name": "get-item",
                "tool": "get_item",
                "params": {"id": "FILL_FROM_t1.results[0].id"},
                "depends_on": "t1",
                "assertions": ["Item has name field"],
            },
        ],
    }))
    return p


class TestWriteCapture:
    def test_creates_three_files(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        response = {"content": [{"type": "text", "text": json.dumps([{"id": 1}])}]}
        entry = write_capture(str(eval_file), "list-items", str(out), response)

        test_dir = out / "list-items"
        assert (test_dir / "response.json").exists()
        assert (test_dir / "timing.json").exists()
        assert (test_dir / "meta.json").exists()

        assert entry["status"] == "success"
        assert entry["tool"] == "list_items"
        assert entry["response_bytes"] > 0

    def test_meta_contains_test_definition(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        write_capture(str(eval_file), "list-items", str(out), {"x": 1})
        meta = json.loads((out / "list-items" / "meta.json").read_text())
        assert meta["test"]["id"] == "t1"
        assert meta["test"]["assertions"] == ["Returns at least one result"]

    def test_detects_mcp_error(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        err = {"isError": True, "content": [{"type": "text", "text": "auth failed"}]}
        entry = write_capture(str(eval_file), "list-items", str(out), err)
        assert entry["status"] == "mcp_error"
        assert "auth failed" in entry["error"]

    def test_unknown_test_name_raises(self, eval_file, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            write_capture(str(eval_file), "no-such-test", str(tmp_path), {})

    def test_duration_passthrough(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        write_capture(str(eval_file), "list-items", str(out), {"x": 1}, duration_ms=123.4)
        timing = json.loads((out / "list-items" / "timing.json").read_text())
        assert timing["duration_ms"] == 123.4

    def test_explicit_tool_definition(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        td = {"name": "list_items", "description": "lists stuff", "inputSchema": {"required": []}}
        write_capture(str(eval_file), "list-items", str(out), {"x": 1}, tool_definition=td)
        meta = json.loads((out / "list-items" / "meta.json").read_text())
        assert meta["tool_definition"]["description"] == "lists stuff"


class TestWriteSkipped:
    def test_returns_skipped_entry(self, eval_file, tmp_path):
        entry = write_skipped(str(eval_file), "get-item", str(tmp_path), "unfilled dep")
        assert entry["status"] == "skipped"
        assert entry["reason"] == "unfilled dep"
        assert entry["tool"] == "get_item"


# ---------------------------------------------------------------------------
# CLI smoke tests - real subprocess invocations exercise argparse + stdin
# ---------------------------------------------------------------------------

class TestCaptureCLI:
    def test_response_via_stdin(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        result = subprocess.run(
            [sys.executable, CAPTURE_PY, str(eval_file), "list-items", str(out)],
            input='{"content": [{"type": "text", "text": "[{\\"id\\":1}]"}]}',
            capture_output=True, text=True, check=True,
        )
        assert "list-items" in result.stdout
        assert (out / "list-items" / "response.json").exists()

    def test_response_via_file(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        resp_path = tmp_path / "resp.json"
        resp_path.write_text('{"id": 1, "name": "x"}')
        result = subprocess.run(
            [sys.executable, CAPTURE_PY, str(eval_file), "list-items",
             str(out), "--response-file", str(resp_path)],
            capture_output=True, text=True, check=True,
        )
        assert result.returncode == 0
        assert (out / "list-items" / "response.json").exists()

    def test_skipped_status(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        result = subprocess.run(
            [sys.executable, CAPTURE_PY, str(eval_file), "get-item", str(out),
             "--status", "skipped", "--reason", "no upstream id"],
            capture_output=True, text=True, check=True,
        )
        entry = json.loads(result.stdout)
        assert entry["status"] == "skipped"


class TestFinalizeRun:
    def test_builds_summary(self, eval_file, tmp_path):
        out = tmp_path / "ws"
        # Capture one success, leave one un-captured (counts as skipped)
        write_capture(
            str(eval_file), "list-items", str(out),
            {"content": [{"type": "text", "text": "[{\"id\":1}]"}]},
        )

        subprocess.run(
            [sys.executable, FINALIZE_PY, str(eval_file), str(out)],
            check=True, capture_output=True, text=True,
        )

        summary = json.loads((out / "run_summary.json").read_text())
        assert summary["server"] == "Test Server"
        assert summary["tests_total"] == 2
        assert summary["tests_run"] == 1
        assert summary["tests_skipped"] == 1
        assert summary["mode"] == "capture"
