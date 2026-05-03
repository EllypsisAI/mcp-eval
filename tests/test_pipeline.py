"""End-to-end pipeline smoke test: capture -> grade -> report."""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


@pytest.fixture
def populated_workspace(tmp_path):
    """Run capture for two tests, then finalize and grade."""
    eval_file = tmp_path / "eval-tests.json"
    eval_file.write_text(json.dumps({
        "server": "Pipeline Test",
        "url": "stdio://test",
        "timestamp": "2026-05-03",
        "tests": [
            {
                "id": "p1",
                "name": "list-stuff",
                "tool": "list_stuff",
                "params": {},
                "assertions": [
                    "Returns at least one result",
                    "Each result has name",
                ],
            },
            {
                "id": "p2",
                "name": "list-empty",
                "tool": "list_other",
                "params": {},
                "assertions": ["Returns at least one result"],
            },
        ],
    }))

    workspace = tmp_path / "ws"

    # capture test 1 - successful
    subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "capture.py"),
         str(eval_file), "list-stuff", str(workspace)],
        input=json.dumps({
            "content": [{
                "type": "text",
                "text": json.dumps([{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]),
            }],
        }),
        text=True, capture_output=True, check=True,
    )

    # capture test 2 - empty array (assertion will fail)
    subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "capture.py"),
         str(eval_file), "list-empty", str(workspace)],
        input=json.dumps({"content": [{"type": "text", "text": "[]"}]}),
        text=True, capture_output=True, check=True,
    )

    # finalize the run summary
    subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "finalize_run.py"),
         str(eval_file), str(workspace)],
        check=True, capture_output=True, text=True,
    )

    return workspace


def test_pipeline_capture_grade_report(populated_workspace):
    workspace = populated_workspace

    # grade
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "grade.py"), str(workspace)],
        capture_output=True, text=True, check=True,
    )
    assert "list-stuff" in result.stdout

    grades_summary = json.loads((workspace / "grades_summary.json").read_text())
    assert grades_summary["total_tests"] == 2
    # list-stuff: 2/2 pass. list-empty: 0/1 pass.
    assert grades_summary["total_passed"] == 2
    assert grades_summary["total_failed"] == 1

    list_stuff_grading = json.loads((workspace / "list-stuff" / "grading.json").read_text())
    assert list_stuff_grading["summary"]["passed"] == 2

    list_empty_grading = json.loads((workspace / "list-empty" / "grading.json").read_text())
    assert list_empty_grading["summary"]["passed"] == 0

    # report
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "report.py"), str(workspace)],
        capture_output=True, text=True, check=True,
    )
    report_html = (workspace / "eval-report.html").read_text()
    assert "list-stuff" in report_html
    assert "list-empty" in report_html
    assert "Pipeline Test" in report_html
