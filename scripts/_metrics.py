"""Shared metric helpers used by run.py (HTTP runner) and capture.py (Claude-mode runner).

The two runners produce the same workspace shape:
    <workspace>/<test-name>/response.json   - raw MCP tool response
    <workspace>/<test-name>/timing.json     - bytes, tokens, fields, duration
    <workspace>/<test-name>/meta.json       - test definition + tool definition

This module owns the timing/field bookkeeping so both runners stay in sync.
"""

import json

CHARS_PER_TOKEN = 4
MAX_FIELDS_IN_TIMING = 50


def count_fields(obj, prefix=""):
    """Recursively enumerate field paths in a JSON structure.

    Lists collapse to their first element so a 1000-item array of identical
    shapes produces one path per field, not 1000.
    """
    fields = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            fields.append(path)
            fields.extend(count_fields(v, path))
    elif isinstance(obj, list) and obj:
        fields.extend(count_fields(obj[0], f"{prefix}[0]"))
    return fields


def parse_inner_payload(response):
    """Extract the inner JSON from an MCP tool response wrapper.

    MCP wraps tool data as: {"content": [{"type": "text", "text": "<json string>"}]}.
    Returns (inner_obj, inner_text) where inner_obj is the parsed JSON or None
    if the text isn't valid JSON, and inner_text is the raw text payload.
    For non-MCP-wrapped responses, returns (response, None).
    """
    if not isinstance(response, dict):
        return response, None

    content = response.get("content")
    if not isinstance(content, list) or not content:
        return response, None

    first = content[0] if isinstance(content[0], dict) else {}
    text = first.get("text", "")
    if not isinstance(text, str):
        return response, None

    try:
        return json.loads(text), text
    except (json.JSONDecodeError, TypeError):
        return None, text


def compute_timing(response, raw_text=None, duration_ms=None):
    """Build a timing.json dict from a tool response.

    Args:
        response: Parsed JSON of the tool response (dict/list).
        raw_text: Raw response string (e.g. SSE wire bytes). If None, the
            JSON-serialized response is used as the byte source.
        duration_ms: Wall-clock duration of the tool call. None for
            Claude-mode captures where we can't measure latency.

    Returns:
        dict matching the timing.json schema.
    """
    if raw_text is None:
        raw_text = json.dumps(response, ensure_ascii=False)

    response_bytes = len(raw_text.encode("utf-8"))
    response_chars = len(raw_text)
    estimated_tokens = response_chars // CHARS_PER_TOKEN

    inner, inner_text = parse_inner_payload(response)
    if inner is not None:
        fields = count_fields(inner)
    else:
        fields = count_fields(response)

    if inner_text is not None:
        payload_bytes = len(inner_text.encode("utf-8"))
    else:
        payload_bytes = response_bytes

    timing = {
        "duration_ms": duration_ms,
        "response_bytes": response_bytes,
        "response_payload_bytes": payload_bytes,
        "response_chars": response_chars,
        "estimated_tokens": estimated_tokens,
        "field_count": len(fields),
        "fields": fields[:MAX_FIELDS_IN_TIMING],
    }
    return timing


def detect_mcp_error(response):
    """Detect whether a tool response represents an error.

    Returns (is_error, error_message). For MCP `isError: true` responses, the
    error message is extracted from content[0].text (first line, capped).
    JSON-RPC errors with no result also count as errors.
    """
    if not isinstance(response, dict):
        return False, None

    if response.get("isError"):
        content = response.get("content", [])
        if isinstance(content, list) and content:
            text = content[0].get("text", "") if isinstance(content[0], dict) else ""
            return True, text.split("\n")[0][:300]
        return True, "MCP tool error (no message)"

    if "error" in response and "result" not in response:
        err = response["error"]
        if isinstance(err, dict):
            return True, str(err.get("message", err))[:300]
        return True, str(err)[:300]

    return False, None
