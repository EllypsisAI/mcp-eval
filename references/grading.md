# Grading System

The grading system evaluates each test's response against its assertions, producing a structured verdict per test.

## Two grading paths

| Path | When | How |
|------|------|-----|
| **Programmatic** | Assertion can be checked against JSON structure | `scripts/grade.py` parses the response and checks |
| **LLM judgment** | Assertion requires semantic understanding | Grader agent (from `agents/grader.md`) reads response + context |

The grading script tries programmatic checks first. Assertions it can't resolve programmatically get flagged for LLM grading.

## Programmatic grading rules

The script reads `response.json` and `meta.json` for each test, then applies pattern matching on the assertion text:

| Assertion pattern | Check |
|-------------------|-------|
| "Returns at least N ..." | Top-level array or `content[0].text` parsed as JSON — check length >= N |
| "Returns N or fewer ..." | Array length <= N |
| "X present" / "X visible" / "X included" | Recursive key search for X in response |
| "Each result has X" / "Each contact has X" | Key X exists on every element of the primary array |
| "Tags embedded" / "Tags included" | Key "tags" exists somewhere in response |
| "Response bytes < N" | Check `timing.json` response_bytes |

If the assertion doesn't match any known pattern, it's marked `"method": "llm"` and deferred to the grader agent.

## grading.json output format

Each test directory gets a `grading.json` file:

```json
{
  "test_id": "read-1",
  "test_name": "search-known-company",
  "status": "pass",
  "assertions": [
    {
      "text": "Returns at least one result",
      "passed": true,
      "evidence": "Response array contains 3 items"
    },
    {
      "text": "Contact type distinguishable",
      "passed": true,
      "evidence": "Each result has 'type' field with values 'person' or 'organisation'"
    },
    {
      "text": "Tags embedded in response",
      "passed": false,
      "evidence": "No 'tags' key found in any response object"
    }
  ],
  "pass_count": 2,
  "fail_count": 1,
  "total": 3
}
```

### Field definitions

| Field | Type | Description |
|-------|------|-------------|
| `test_id` | string | Matches the test's `id` from the eval file |
| `test_name` | string | Matches the test's `name` |
| `status` | string | `"pass"` (all assertions pass), `"fail"` (any fails), `"partial"` (mixed), `"error"` (test didn't run) |
| `assertions` | array | One entry per assertion |
| `assertions[].text` | string | The original assertion text from the test file |
| `assertions[].passed` | boolean | Whether the assertion holds |
| `assertions[].evidence` | string | What was found (or not found) — the "why" behind the verdict |
| `pass_count` | number | Count of passed assertions |
| `fail_count` | number | Count of failed assertions |
| `total` | number | Total assertion count |

### Status logic

- All assertions pass: `"pass"`
- All assertions fail: `"fail"`
- Mixed results: `"partial"`
- Test errored during run (no response): `"error"`

## LLM grading via the grader agent

For assertions deferred to LLM judgment, the grader agent receives:

1. The assertion text
2. The full `response.json`
3. The `meta.json` (test definition + tool schema)
4. The `context` field from the top-level eval file

The grader returns the same `{text, passed, evidence}` structure. Its evidence should quote specific parts of the response that support the verdict.

## How grading appears in the report

The HTML report reads `grading.json` from each test directory and displays:
- A colored badge per test: green (pass), red (fail), yellow (partial)
- Expandable assertion list with pass/fail icons and evidence text
- Aggregate stats: total assertions, pass rate, common failure patterns
