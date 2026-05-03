---
name: eval-grade
description: Grade MCP eval responses against their assertions using programmatic checks and LLM judgment.
arguments:
  - name: workspace
    description: Path to the eval-workspace directory (default: eval-workspace)
    required: false
---

# /eval-grade

Score every test response against its assertions.

## Steps

1. **Load results** — Read `run_summary.json` from the workspace. Skip tests that errored or were skipped during the run.

2. **Programmatic grading** — Run the grading script:
   ```bash
   python3 scripts/grade.py <workspace>
   ```
   This handles assertions that can be checked structurally: field presence, result counts, type checks, byte thresholds.

3. **LLM grading** — For assertions that need judgment (semantic quality, usefulness, completeness), spawn a grader agent with `agents/grader.md`. The grader reads each test's `response.json`, `meta.json`, and the assertion text, then returns pass/fail with evidence.

4. **Write results** — Each test directory gets a `grading.json`:
   ```json
   {
     "test_id": "read-1",
     "test_name": "search-known-company",
     "status": "pass",
     "assertions": [
       {"text": "Returns at least one result", "passed": true, "evidence": "Response contains 3 results"},
       {"text": "Tags embedded", "passed": false, "evidence": "No 'tags' field in response objects"}
     ],
     "pass_count": 4,
     "fail_count": 1,
     "total": 5
   }
   ```

5. **Present summary** — Show a grading overview:

   | Test | Pass | Fail | Status |
   |------|------|------|--------|
   | search-known-company | 4 | 1 | PARTIAL |
   | list-contacts-page | 4 | 0 | PASS |

   Highlight failures — these are the findings that matter.

6. **Next step** — Tell the user: "Run `/eval-report` to generate the visual dashboard."

## Grading reference

Load `references/grading.md` for the full grading schema, assertion types, and how programmatic vs LLM grading works.
