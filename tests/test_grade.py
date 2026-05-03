"""Tests for scripts/grade.py - assertion grading logic."""

import json
import os
import tempfile

import pytest

from grade import (
    _normalize_field_name,
    check_each_has_field,
    check_field_present,
    check_ids_present,
    check_includes_or_links,
    check_returns_results,
    check_type_distinguishable,
    extract_items,
    find_field,
    grade_test,
    grade_workspace,
    parse_mcp_response,
)


# ---------------------------------------------------------------------------
# parse_mcp_response
# ---------------------------------------------------------------------------

class TestParseMcpResponse:
    def test_wrapped_json_array(self):
        wrapped = {"content": [{"type": "text", "text": '[{"id": 1}]'}]}
        data, is_err, msg = parse_mcp_response(wrapped)
        assert data == [{"id": 1}]
        assert is_err is False
        assert msg is None

    def test_error_response(self):
        wrapped = {
            "isError": True,
            "content": [{"type": "text", "text": "Bad params: missing field 'id'"}],
        }
        _, is_err, msg = parse_mcp_response(wrapped)
        assert is_err is True
        assert msg == "Bad params: missing field 'id'"

    def test_non_json_text(self):
        wrapped = {"content": [{"type": "text", "text": "plain text response"}]}
        data, is_err, msg = parse_mcp_response(wrapped)
        assert data == "plain text response"
        assert is_err is False

    def test_non_dict(self):
        data, is_err, msg = parse_mcp_response([1, 2, 3])
        assert data == [1, 2, 3]
        assert is_err is False


# ---------------------------------------------------------------------------
# extract_items
# ---------------------------------------------------------------------------

class TestExtractItems:
    def test_direct_array(self):
        assert extract_items([{"id": 1}, {"id": 2}]) == [{"id": 1}, {"id": 2}]

    def test_singleton_wrapping_array(self):
        # [{ "results": [...] }] is a common wrapper shape
        assert extract_items([{"results": [{"id": 1}]}]) == [{"id": 1}]

    def test_object_with_array_value(self):
        assert extract_items({"items": [{"id": 1}, {"id": 2}]}) == [{"id": 1}, {"id": 2}]

    def test_object_no_array(self):
        # Falls back to wrapping the object as a single item
        assert extract_items({"id": 1, "name": "x"}) == [{"id": 1, "name": "x"}]

    def test_primitive(self):
        assert extract_items("plain") == []


# ---------------------------------------------------------------------------
# find_field
# ---------------------------------------------------------------------------

class TestFindField:
    def test_top_level(self):
        results = find_field({"id": 42, "name": "x"}, "id")
        assert ("id", 42) in results

    def test_nested(self):
        obj = {"user": {"profile": {"id": 99}}}
        results = find_field(obj, "id")
        paths = [p for p, _ in results]
        assert "user.profile.id" in paths

    def test_case_insensitive_default(self):
        results = find_field({"ID": 1}, "id")
        assert results[0][1] == 1

    def test_in_list(self):
        obj = [{"id": 1}, {"id": 2}]
        results = find_field(obj, "id")
        # Searches first 3 list items
        assert len(results) == 2

    def test_missing_field(self):
        assert find_field({"a": 1}, "b") == []


# ---------------------------------------------------------------------------
# _normalize_field_name (generic only - no server-specific mappings)
# ---------------------------------------------------------------------------

class TestNormalizeFieldName:
    def test_single_word(self):
        candidates = _normalize_field_name("status")
        assert "status" in candidates

    def test_multi_word_camel(self):
        candidates = _normalize_field_name("created at")
        assert "createdAt" in candidates
        assert "created_at" in candidates
        assert "created" in candidates
        assert "at" in candidates

    def test_strips_extra_whitespace(self):
        candidates = _normalize_field_name("  email  address  ")
        assert "emailAddress" in candidates
        assert "email_address" in candidates

    def test_no_capsule_specific_mappings(self):
        # We deliberately removed CRM-specific mappings. Caller passes "tag names",
        # we return generic transforms only - not Capsule-specific "tags"+"name".
        candidates = _normalize_field_name("tag names")
        assert "tagNames" in candidates
        # The bare word "tags" (Capsule's array name) is NOT in the generic transforms
        # of "tag names" - it's just "tag" and "names" individually
        assert "tag" in candidates
        assert "names" in candidates

    def test_dedup_preserves_order(self):
        candidates = _normalize_field_name("foo")
        # Description-as-is and the single word are the same; deduped to one
        assert candidates.count("foo") == 1


# ---------------------------------------------------------------------------
# Programmatic checkers
# ---------------------------------------------------------------------------

class TestCheckReturnsResults:
    def test_at_least_one_pass(self):
        can, passed, ev = check_returns_results(
            "Returns at least one result", None, [{"id": 1}]
        )
        assert can is True
        assert passed is True
        assert "1" in ev

    def test_at_least_one_fail(self):
        can, passed, _ = check_returns_results(
            "Returns at least one result", None, []
        )
        assert can is True
        assert passed is False

    def test_n_or_fewer(self):
        can, passed, _ = check_returns_results(
            "Returns 5 or fewer results", None, [1, 2, 3]
        )
        assert can is True
        assert passed is True

    def test_n_or_fewer_violated(self):
        can, passed, _ = check_returns_results(
            "Returns 2 or fewer results", None, [1, 2, 3]
        )
        assert can is True
        assert passed is False

    def test_returns_results_plural(self):
        can, passed, _ = check_returns_results("Returns results", None, [{"id": 1}])
        assert can is True
        assert passed is True

    def test_does_not_match_unrelated(self):
        can, passed, _ = check_returns_results(
            "Each item has an ID", None, [{"id": 1}]
        )
        assert can is False


class TestCheckIdsPresent:
    def test_pass(self):
        can, passed, _ = check_ids_present(
            "IDs present", None, [{"id": 1}, {"id": 2}]
        )
        assert can is True
        assert passed is True

    def test_fail_missing(self):
        can, passed, _ = check_ids_present(
            "ID field present", None, [{"id": 1}, {"name": "x"}]
        )
        assert can is True
        assert passed is False

    def test_no_id_in_assertion(self):
        can, _, _ = check_ids_present("Returns data", None, [{"id": 1}])
        assert can is False


class TestCheckEachHasField:
    def test_pass(self):
        can, passed, _ = check_each_has_field(
            "Each result has name",
            None,
            [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
        )
        assert can is True
        assert passed is True

    def test_missing_in_one_item(self):
        can, passed, _ = check_each_has_field(
            "Each result has name",
            None,
            [{"id": 1, "name": "a"}, {"id": 2}],
        )
        assert can is True
        assert passed is False

    def test_camelcase_match(self):
        # "Each item has created at" should find "createdAt"
        can, passed, _ = check_each_has_field(
            "Each item has created at",
            None,
            [{"createdAt": "2026-01-01"}, {"createdAt": "2026-01-02"}],
        )
        assert can is True
        assert passed is True


class TestCheckTypeDistinguishable:
    def test_multiple_types(self):
        can, passed, ev = check_type_distinguishable(
            "Type is distinguishable",
            None,
            [{"type": "person"}, {"type": "organisation"}],
        )
        assert can is True
        assert passed is True
        assert "2 distinct types" in ev

    def test_single_type_still_passes(self):
        can, passed, _ = check_type_distinguishable(
            "Type distinguishable", None, [{"type": "person"}]
        )
        assert can is True
        assert passed is True

    def test_no_type_field(self):
        can, passed, _ = check_type_distinguishable(
            "Type distinguishable", None, [{"id": 1}]
        )
        assert can is True
        assert passed is False


class TestCheckIncludesOrLinks:
    def test_pass(self):
        items = [{"id": 1, "tags": ["a", "b"]}]
        can, passed, _ = check_includes_or_links(
            "Response includes or links to tags", {"items": items}, items
        )
        assert can is True
        assert passed is True


class TestCheckFieldPresent:
    def test_simple_field(self):
        can, passed, _ = check_field_present(
            "Status present", None, [{"status": "active"}]
        )
        assert can is True
        assert passed is True

    def test_strips_qualifiers(self):
        can, passed, _ = check_field_present(
            "Tags included (via embed)", None, [{"tags": ["x"]}]
        )
        assert can is True
        assert passed is True

    def test_strips_with_clause(self):
        can, passed, _ = check_field_present(
            "Due date present without embeds", None, [{"dueDate": "2026-01-01"}]
        )
        assert can is True
        assert passed is True


# ---------------------------------------------------------------------------
# grade_test - end-to-end on a fixture directory
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path):
    """Build a fake test workspace with one passing and one failing test."""
    test_a = tmp_path / "test-a"
    test_a.mkdir()
    (test_a / "response.json").write_text(json.dumps({
        "content": [{
            "type": "text",
            "text": json.dumps([{"id": 1, "name": "Acme"}, {"id": 2, "name": "Beta"}]),
        }],
    }))
    (test_a / "meta.json").write_text(json.dumps({
        "test": {
            "id": "a",
            "name": "test-a",
            "tool": "list_things",
            "params": {},
            "assertions": [
                "Returns at least one result",
                "Each result has name",
                "IDs present",
            ],
        },
        "tool_definition": {"name": "list_things"},
    }))

    test_b = tmp_path / "test-b"
    test_b.mkdir()
    (test_b / "response.json").write_text(json.dumps({
        "isError": True,
        "content": [{"type": "text", "text": "Permission denied"}],
    }))
    (test_b / "meta.json").write_text(json.dumps({
        "test": {
            "id": "b",
            "name": "test-b",
            "tool": "list_secret",
            "params": {},
            "assertions": ["Returns at least one result"],
        },
        "tool_definition": {"name": "list_secret"},
    }))

    return tmp_path


class TestGradeTest:
    def test_passing_test(self, workspace):
        grading, needs_llm = grade_test(str(workspace / "test-a"))
        assert grading["summary"]["total"] == 3
        assert grading["summary"]["passed"] == 3
        assert grading["summary"]["failed"] == 0
        assert needs_llm == []

    def test_error_response_fails_all(self, workspace):
        grading, _ = grade_test(str(workspace / "test-b"))
        assert grading["summary"]["passed"] == 0
        assert grading["summary"]["failed"] == 1
        assert grading["error_context"]["is_error"] is True
        assert "Permission denied" in grading["error_context"]["error_message"]

    def test_missing_files_returns_none(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        grading, needs_llm = grade_test(str(empty))
        assert grading is None
        assert needs_llm == []


class TestGradeWorkspace:
    def test_writes_per_test_grading(self, workspace, capsys):
        summary = grade_workspace(str(workspace))
        assert (workspace / "test-a" / "grading.json").exists()
        assert (workspace / "test-b" / "grading.json").exists()
        assert (workspace / "grades_summary.json").exists()

        assert summary["total_tests"] == 2
        assert summary["total_passed"] == 3
        assert summary["total_failed"] == 1
        assert "test-b" in summary["error_tests"]
