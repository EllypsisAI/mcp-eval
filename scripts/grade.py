#!/usr/bin/env python3
"""
MCP Eval Grader

Walks an eval-workspace directory, reads response.json + meta.json per test,
evaluates assertions programmatically where possible, flags the rest for LLM.

Usage:
    python3 grade.py <eval-workspace-dir>

Produces per-test:
    <test-dir>/grading.json       -- per-assertion results

Produces workspace-level:
    <workspace-dir>/grades_summary.json  -- aggregated results
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _metrics import detect_mcp_error, parse_inner_payload  # noqa: E402


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_mcp_response(response):
    """Extract the inner data from an MCP tool response.

    MCP responses wrap data as:
      { "content": [{ "type": "text", "text": "<json-string>" }] }

    Returns (data, is_error, error_msg):
      - data: parsed inner JSON (dict/list) or raw text string
      - is_error: bool
      - error_msg: first line of error text if is_error
    """
    is_error, error_msg = detect_mcp_error(response)
    inner_obj, inner_text = parse_inner_payload(response)

    if is_error:
        return (inner_text if inner_text is not None else response), True, error_msg

    if inner_obj is not None:
        return inner_obj, False, None

    if inner_text is not None:
        return inner_text, False, None

    return response, False, None


def extract_items(data):
    """Extract the main list of items from parsed MCP data.

    Generic wrapper-unwrapping. Common shapes:
      - [...] direct array               -> the array itself
      - [{ "key": [...] }] singleton     -> the inner array
      - { "key": [...] } object          -> the first array value
    """
    if isinstance(data, list):
        # Check if it's the wrapper pattern: [{ "someKey": [...] }]
        if len(data) == 1 and isinstance(data[0], dict):
            inner = data[0]
            # Find the first array value
            for v in inner.values():
                if isinstance(v, list):
                    return v
            # No array found, return the dict as a single-item list
            return [inner]
        return data

    if isinstance(data, dict):
        # Find the first array value
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]

    return []


def find_field(obj, field_name, case_insensitive=True):
    """Recursively search for a field in a nested dict/list.

    Returns list of (path, value) tuples.
    """
    results = []
    _find_field_recursive(obj, field_name, "", results, case_insensitive)
    return results


def _find_field_recursive(obj, field_name, path, results, case_insensitive):
    target = field_name.lower() if case_insensitive else field_name

    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else k
            k_cmp = k.lower() if case_insensitive else k
            if k_cmp == target:
                results.append((current_path, v))
            _find_field_recursive(v, field_name, current_path, results, case_insensitive)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):  # Check first 3 items only
            _find_field_recursive(item, field_name, f"{path}[{i}]", results, case_insensitive)


# ---------------------------------------------------------------------------
# Assertion patterns -> programmatic checks
# ---------------------------------------------------------------------------

# Each pattern returns (can_check, passed, evidence) or (False, None, None)

def check_returns_results(assertion, data, items):
    """Handle: 'Returns at least one result', 'Returns results', 'Returns entries'."""
    patterns = [
        r"returns?\s+(at\s+least\s+)?(one|\d+)\s+result",
        r"returns?\s+results",
        r"returns?\s+data",
        r"returns?\s+entries",
        r"returns?\s+\w+s?\s*$",  # "Returns contacts", "Returns tasks", etc.
    ]

    # Also handle quantity assertions like "Returns 2 or fewer results"
    qty_match = re.search(r"returns?\s+(\d+)\s+or\s+(fewer|less|more)\s+", assertion, re.IGNORECASE)
    if qty_match:
        threshold = int(qty_match.group(1))
        direction = qty_match.group(2).lower()
        count = len(items)
        if direction in ("fewer", "less"):
            passed = count <= threshold
            return True, passed, f"Response contains {count} items (threshold: <= {threshold})"
        else:
            passed = count >= threshold
            return True, passed, f"Response contains {count} items (threshold: >= {threshold})"

    for p in patterns:
        if re.search(p, assertion, re.IGNORECASE):
            count = len(items)
            if count > 0:
                return True, True, f"Response contains {count} items"
            else:
                return True, False, "Response contains 0 items"
    return False, None, None


def check_field_present(assertion, data, items):
    """Handle: 'X present', 'X visible', 'X included', 'X available'."""
    patterns = [
        r"(.+?)\s+(?:is\s+)?(?:present|visible|included|available)(?:\s|$)",
        r"(?:has|have|contains?|includes?)\s+(?:an?\s+)?(.+?)(?:\s+field)?$",
    ]
    for p in patterns:
        m = re.search(p, assertion, re.IGNORECASE)
        if m:
            field_desc = m.group(1).strip().rstrip(".")
            # Strip context qualifiers: "X present without embeds" -> "X"
            field_desc = re.sub(
                r"\s+(?:without|with|via|from|in|for|after|before)\b.*$",
                "", field_desc, flags=re.IGNORECASE,
            )
            # Strip parenthetical qualifiers: "Tags included (via embed)" -> "Tags"
            field_desc = re.sub(r"\s*\(.*?\)\s*", "", field_desc)
            field_desc = field_desc.strip()
            if field_desc:
                return _check_field_in_data(field_desc, data, items)
    return False, None, None


def check_each_has_field(assertion, data, items):
    """Handle: 'Each result has X', 'Every item has X'."""
    m = re.search(
        r"each\s+(?:result|item|record|entry)\s+has\s+(?:an?\s+)?(.+?)(?:\s+field)?$",
        assertion, re.IGNORECASE,
    )
    if not m:
        return False, None, None

    field_desc = m.group(1).strip()
    field_names = _normalize_field_name(field_desc)

    if not items:
        return True, False, "No items in response to check"

    # Direct top-level: every item has the field (universal quantifier)
    for fn in field_names:
        all_have = all(
            isinstance(item, dict) and fn in item and item[fn] is not None
            for item in items
        )
        if all_have:
            sample = items[0].get(fn) if isinstance(items[0], dict) else None
            return True, True, f"All {len(items)} items have '{fn}' field (sample: {_trunc(sample)})"

    # Nested fallback: every item must have the field somewhere in its tree.
    # We deliberately keep this universally-quantified - "each result has X"
    # means each, not "the first item has X."
    for fn in field_names:
        all_have_nested = all(find_field(item, fn) for item in items)
        if all_have_nested:
            path, val = find_field(items[0], fn)[0]
            return True, True, f"All {len(items)} items have '{fn}' (sample: {path}={_trunc(val)})"

    return True, False, f"Field '{field_desc}' not found in every item"


def check_ids_present(assertion, data, items):
    """Handle: 'IDs present', 'ID field', 'has an ID'."""
    if not re.search(r"\bIDs?\b", assertion, re.IGNORECASE):
        return False, None, None

    if not items:
        return True, False, "No items to check for IDs"

    has_id = all(
        isinstance(item, dict) and item.get("id") is not None
        for item in items
    )
    if has_id:
        sample_id = items[0].get("id") if items else None
        return True, True, f"All {len(items)} items have 'id' field (sample: {sample_id})"

    return True, False, "Some items missing 'id' field"


def check_type_distinguishable(assertion, data, items):
    """Handle: 'type is distinguishable', 'type distinguishable'."""
    if not re.search(r"type.*distinguishable|distinguishable.*type", assertion, re.IGNORECASE):
        return False, None, None

    if not items:
        return True, False, "No items to check types"

    types = set()
    for item in items:
        if isinstance(item, dict) and "type" in item:
            types.add(item["type"])

    if len(types) > 1:
        return True, True, f"Found {len(types)} distinct types: {sorted(types)}"
    elif len(types) == 1:
        # Single type is still distinguishable if the field exists
        return True, True, f"Type field present with value: {types.pop()}"
    else:
        return True, False, "No 'type' field found in items"


def check_basic_fields(assertion, data, items):
    """Handle: 'Basic X fields present', 'Returns a list of X'."""
    m = re.search(r"basic\s+\w+\s+fields?\s+present", assertion, re.IGNORECASE)
    if not m:
        # Also handle "Returns a list of X"
        m2 = re.search(r"returns?\s+a\s+list\s+of\s+(\w+)", assertion, re.IGNORECASE)
        if m2:
            count = len(items)
            if count > 0:
                return True, True, f"Response contains a list of {count} items"
            else:
                return True, False, "Response contains 0 items"
        return False, None, None

    if not items:
        return True, False, "No items in response"

    # Check that items have multiple fields (basic sanity)
    if isinstance(items[0], dict):
        field_count = len(items[0])
        fields_sample = list(items[0].keys())[:8]
        if field_count >= 3:
            return True, True, f"Items have {field_count} fields: {fields_sample}"
        else:
            return True, False, f"Items only have {field_count} fields: {fields_sample}"

    return True, False, "Items are not objects with fields"


def check_includes_or_links(assertion, data, items):
    """Handle: 'Response includes or links to X'."""
    m = re.search(r"(?:includes?|contains?)\s+or\s+links?\s+to\s+(.+)", assertion, re.IGNORECASE)
    if not m:
        return False, None, None

    target = m.group(1).strip().rstrip(".")
    field_names = _normalize_field_name(target)

    # Check in items
    for fn in field_names:
        for item in items[:5]:
            if isinstance(item, dict):
                hits = find_field(item, fn)
                if hits:
                    path, val = hits[0]
                    return True, True, f"Found '{fn}' at {path} (sample: {_trunc(val)})"

    # Check in top-level data
    for fn in field_names:
        hits = find_field(data, fn)
        if hits:
            path, val = hits[0]
            return True, True, f"Found '{fn}' at {path}"

    return True, False, f"No field matching '{target}' found in response"


# Ordered list of checkers. First match wins.
CHECKERS = [
    check_returns_results,
    check_basic_fields,
    check_each_has_field,
    check_ids_present,
    check_type_distinguishable,
    check_includes_or_links,
    check_field_present,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_field_name(desc):
    """Turn a human description into candidate field names.

    Generic transforms only - we deliberately avoid hardcoding mappings for
    any specific server's schema. Anything that needs server-specific
    knowledge belongs in LLM grading.

    'Organisation name' -> ['organisation name', 'organisation', 'name',
                            'organisationName', 'organisation_name']
    'Phone numbers'     -> ['phone numbers', 'phone', 'numbers',
                            'phoneNumbers', 'phone_numbers']
    'created at'        -> ['created at', 'created', 'at',
                            'createdAt', 'created_at']
    """
    desc_lower = desc.lower().strip()
    words = [w for w in re.split(r"\s+", desc_lower) if w]
    candidates = [desc_lower]

    # Each word individually
    candidates.extend(words)

    # Common API casing variants when the description has multiple words
    if len(words) > 1:
        camel = words[0] + "".join(w.capitalize() for w in words[1:])
        candidates.append(camel)
        candidates.append("_".join(words))

    # Deduplicate, preserve order
    seen = set()
    unique = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _check_field_in_data(field_desc, data, items):
    """Check if a described field exists in the data."""
    field_names = _normalize_field_name(field_desc)

    # Check in items first
    for fn in field_names:
        for item in items[:5]:
            if isinstance(item, dict):
                hits = find_field(item, fn)
                if hits:
                    path, val = hits[0]
                    if val is not None and val != "" and val != []:
                        return True, True, f"Found '{fn}' at {path} (sample: {_trunc(val)})"

    # Check top-level data
    for fn in field_names:
        hits = find_field(data, fn)
        if hits:
            path, val = hits[0]
            if val is not None and val != "" and val != []:
                return True, True, f"Found '{fn}' at {path}"

    # Check for presence even if empty (still counts as "present" for some assertions)
    for fn in field_names:
        for item in items[:5]:
            if isinstance(item, dict):
                hits = find_field(item, fn)
                if hits:
                    path, val = hits[0]
                    return True, True, f"Found '{fn}' at {path} (value: {_trunc(val)})"

    return True, False, f"No field matching '{field_desc}' found in response"


def _trunc(val, max_len=100):
    """Truncate a value for evidence strings."""
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# ---------------------------------------------------------------------------
# Grading logic
# ---------------------------------------------------------------------------

def grade_test(test_dir):
    """Grade a single test directory. Returns (grading_dict, needs_llm_assertions)."""
    meta_path = os.path.join(test_dir, "meta.json")
    response_path = os.path.join(test_dir, "response.json")

    if not os.path.exists(meta_path) or not os.path.exists(response_path):
        return None, []

    with open(meta_path) as f:
        meta = json.load(f)

    with open(response_path) as f:
        response = json.load(f)

    test = meta.get("test", {})
    assertions = test.get("assertions", [])

    # Parse the response
    data, is_error, error_msg = parse_mcp_response(response)
    items = [] if is_error else extract_items(data)

    expectations = []
    needs_llm = []

    for assertion in assertions:
        if is_error:
            expectations.append({
                "text": assertion,
                "passed": False,
                "evidence": f"Response is an error: {error_msg}",
            })
            continue

        # Try each programmatic checker
        graded = False
        for checker in CHECKERS:
            can_check, passed, evidence = checker(assertion, data, items)
            if can_check:
                expectations.append({
                    "text": assertion,
                    "passed": passed,
                    "evidence": evidence,
                })
                graded = True
                break

        if not graded:
            # Flag for LLM judgment
            needs_llm.append(assertion)
            expectations.append({
                "text": assertion,
                "passed": None,  # Indeterminate — needs LLM
                "evidence": "NEEDS_LLM_JUDGMENT: Could not evaluate programmatically",
            })

    # Resolve indeterminate assertions conservatively (fail them)
    for exp in expectations:
        if exp["passed"] is None:
            exp["passed"] = False
            exp["evidence"] += " (defaulted to FAIL)"

    passed = sum(1 for e in expectations if e["passed"])
    failed = sum(1 for e in expectations if not e["passed"])
    total = len(expectations)

    grading = {
        "expectations": expectations,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": total,
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0,
        },
    }

    # Add error context if applicable
    if is_error:
        grading["error_context"] = {
            "is_error": True,
            "error_message": error_msg,
            "test_tool": test.get("tool"),
            "test_params": test.get("params"),
        }

    return grading, needs_llm


def grade_workspace(workspace_dir):
    """Grade all tests in an eval-workspace directory."""
    results = {}
    all_needs_llm = {}
    total_passed = 0
    total_failed = 0
    total_tests = 0
    total_assertions = 0
    error_tests = []

    # Find all test directories (dirs with both meta.json and response.json)
    for entry in sorted(os.listdir(workspace_dir)):
        test_dir = os.path.join(workspace_dir, entry)
        if not os.path.isdir(test_dir):
            continue

        meta_path = os.path.join(test_dir, "meta.json")
        response_path = os.path.join(test_dir, "response.json")
        if not os.path.exists(meta_path) or not os.path.exists(response_path):
            continue

        grading, needs_llm = grade_test(test_dir)
        if grading is None:
            continue

        test_name = entry
        results[test_name] = grading

        # Write per-test grading.json
        grading_path = os.path.join(test_dir, "grading.json")
        with open(grading_path, "w") as f:
            json.dump(grading, f, indent=2)

        summary = grading["summary"]
        total_passed += summary["passed"]
        total_failed += summary["failed"]
        total_assertions += summary["total"]
        total_tests += 1

        if grading.get("error_context", {}).get("is_error"):
            error_tests.append(test_name)

        if needs_llm:
            all_needs_llm[test_name] = needs_llm

        # Print progress
        status = "ERROR" if test_name in error_tests else f"{summary['passed']}/{summary['total']}"
        print(f"  [{status}] {test_name}")

    # Write workspace-level summary
    grades_summary = {
        "workspace": workspace_dir,
        "total_tests": total_tests,
        "total_assertions": total_assertions,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "overall_pass_rate": round(total_passed / total_assertions, 2) if total_assertions > 0 else 0.0,
        "error_tests": error_tests,
        "needs_llm_judgment": all_needs_llm,
        "per_test": {
            name: grading["summary"] for name, grading in results.items()
        },
    }

    summary_path = os.path.join(workspace_dir, "grades_summary.json")
    with open(summary_path, "w") as f:
        json.dump(grades_summary, f, indent=2)

    return grades_summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 grade.py <eval-workspace-dir>")
        print()
        print("Grades all test directories in the workspace.")
        print("Each test dir must contain response.json and meta.json.")
        sys.exit(1)

    workspace_dir = sys.argv[1]

    if not os.path.isdir(workspace_dir):
        print(f"Error: {workspace_dir} is not a directory")
        sys.exit(1)

    print(f"Grading: {workspace_dir}")
    print()

    summary = grade_workspace(workspace_dir)

    print()
    print(f"Results: {summary['total_passed']}/{summary['total_assertions']} assertions passed "
          f"({summary['overall_pass_rate']:.0%})")
    print(f"Tests: {summary['total_tests']} total, {len(summary['error_tests'])} errors")

    if summary["needs_llm_judgment"]:
        llm_count = sum(len(v) for v in summary["needs_llm_judgment"].values())
        print(f"LLM needed: {llm_count} assertions across "
              f"{len(summary['needs_llm_judgment'])} tests")

    print(f"\nSummary: {os.path.join(workspace_dir, 'grades_summary.json')}")


if __name__ == "__main__":
    main()
