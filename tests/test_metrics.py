"""Tests for scripts/_metrics.py - shared timing/parsing helpers."""

import json

from _metrics import (
    compute_timing,
    count_fields,
    detect_mcp_error,
    parse_inner_payload,
)


# ---------------------------------------------------------------------------
# count_fields
# ---------------------------------------------------------------------------

class TestCountFields:
    def test_flat_dict(self):
        assert count_fields({"a": 1, "b": 2}) == ["a", "b"]

    def test_nested_dict(self):
        fields = count_fields({"user": {"id": 1, "name": "x"}})
        assert fields == ["user", "user.id", "user.name"]

    def test_list_uses_first_element(self):
        fields = count_fields([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
        assert fields == ["[0].id", "[0].name"]

    def test_empty_list(self):
        assert count_fields([]) == []

    def test_primitive(self):
        assert count_fields("hello") == []
        assert count_fields(42) == []

    def test_deeply_nested(self):
        fields = count_fields({"a": {"b": {"c": {"d": 1}}}})
        assert fields == ["a", "a.b", "a.b.c", "a.b.c.d"]


# ---------------------------------------------------------------------------
# parse_inner_payload
# ---------------------------------------------------------------------------

class TestParseInnerPayload:
    def test_mcp_wrapped_json(self):
        wrapped = {"content": [{"type": "text", "text": '{"id": 1}'}]}
        obj, text = parse_inner_payload(wrapped)
        assert obj == {"id": 1}
        assert text == '{"id": 1}'

    def test_mcp_wrapped_invalid_json(self):
        wrapped = {"content": [{"type": "text", "text": "not json"}]}
        obj, text = parse_inner_payload(wrapped)
        assert obj is None
        assert text == "not json"

    def test_unwrapped_dict(self):
        plain = {"id": 1, "name": "x"}
        obj, text = parse_inner_payload(plain)
        assert obj == plain
        assert text is None

    def test_empty_content(self):
        obj, text = parse_inner_payload({"content": []})
        assert obj == {"content": []}
        assert text is None

    def test_non_dict(self):
        obj, text = parse_inner_payload([1, 2, 3])
        assert obj == [1, 2, 3]
        assert text is None


# ---------------------------------------------------------------------------
# detect_mcp_error
# ---------------------------------------------------------------------------

class TestDetectMcpError:
    def test_success(self):
        is_err, msg = detect_mcp_error({"content": [{"type": "text", "text": "ok"}]})
        assert is_err is False
        assert msg is None

    def test_is_error_flag(self):
        resp = {
            "isError": True,
            "content": [{"type": "text", "text": "Failed: bad request\nstack..."}],
        }
        is_err, msg = detect_mcp_error(resp)
        assert is_err is True
        assert msg == "Failed: bad request"

    def test_is_error_no_content(self):
        is_err, msg = detect_mcp_error({"isError": True})
        assert is_err is True
        assert "no message" in msg

    def test_jsonrpc_error_no_result(self):
        is_err, msg = detect_mcp_error({"error": {"code": -32601, "message": "not found"}})
        assert is_err is True
        assert "not found" in msg

    def test_jsonrpc_error_with_result_is_not_error(self):
        # If both error and result are present, treat as success
        is_err, _ = detect_mcp_error({"error": {}, "result": {"x": 1}})
        assert is_err is False

    def test_non_dict(self):
        is_err, msg = detect_mcp_error("plain text")
        assert is_err is False
        assert msg is None


# ---------------------------------------------------------------------------
# compute_timing
# ---------------------------------------------------------------------------

class TestComputeTiming:
    def test_basic_unwrapped(self):
        resp = {"id": 1, "name": "test"}
        timing = compute_timing(resp, duration_ms=42.5)
        assert timing["duration_ms"] == 42.5
        assert timing["response_bytes"] > 0
        assert timing["response_bytes"] == timing["response_payload_bytes"]
        assert timing["estimated_tokens"] == timing["response_chars"] // 4
        assert timing["field_count"] == 2

    def test_mcp_wrapped(self):
        inner = {"items": [{"id": 1}, {"id": 2}]}
        wrapped = {"content": [{"type": "text", "text": json.dumps(inner)}]}
        timing = compute_timing(wrapped)
        # Payload bytes should be the inner text, smaller than the full wrapper
        assert timing["response_payload_bytes"] < timing["response_bytes"]
        # Field count comes from the inner data
        assert "items" in timing["fields"]

    def test_no_duration(self):
        timing = compute_timing({"x": 1})
        assert timing["duration_ms"] is None

    def test_field_cap_at_50(self):
        big = {f"key{i}": i for i in range(100)}
        timing = compute_timing(big)
        assert timing["field_count"] == 100  # actual count
        assert len(timing["fields"]) == 50    # but truncated for display

    def test_explicit_raw_text(self):
        # When raw is the SSE wire, response_bytes counts the wire, not the parsed JSON
        resp = {"x": 1}
        raw = "event: data\ndata: " + json.dumps(resp) + "\n\n"
        timing = compute_timing(resp, raw_text=raw)
        assert timing["response_bytes"] == len(raw.encode("utf-8"))
