# Test Case Schema

The eval test file is a JSON document that defines which tools to call, with what params, and what to check in the responses.

## Top-level structure

```json
{
  "server": "human-readable server name",
  "url": "https://example.com/mcp/endpoint",
  "timestamp": "2026-03-06",
  "context": "Why this eval exists and what we're looking for",
  "tests": []
}
```

| Field | Required | Purpose |
|-------|----------|---------|
| `server` | Yes | Display name for reports |
| `url` | Yes | MCP Streamable HTTP endpoint |
| `timestamp` | No | When the test file was created/updated |
| `context` | No | Background for graders — what matters about this server |

## Per-test structure

```json
{
  "id": "read-1",
  "name": "search-known-company",
  "tool": "search_contacts",
  "params": {"q": "Acme", "page": "1", "perPage": "10"},
  "workflow_step": "Search whether a known company exists in the CRM",
  "depends_on": null,
  "assertions": [
    "Returns at least one result",
    "Each result has an ID field usable for follow-up calls"
  ]
}
```

| Field | Required | Purpose |
|-------|----------|---------|
| `id` | Yes | Unique identifier, used in `depends_on` references |
| `name` | Yes | Descriptive slug, becomes the output directory name |
| `tool` | Yes | Exact MCP tool name to call |
| `params` | Yes | Arguments passed to `tools/call`. Use `{}` for no-param tools |
| `workflow_step` | No | What this test validates in a real workflow |
| `depends_on` | No | Test ID whose output feeds this test's params |
| `assertions` | Yes | What to check in the response (list of strings) |

## Params and dependencies

For tests that need output from a prior test, use the `FILL_FROM_` convention:

```json
{
  "id": "read-2b",
  "name": "get-contact-by-id",
  "tool": "get_contact",
  "params": {"contactId": "FILL_FROM_read-1.results[0].id"},
  "depends_on": "read-1"
}
```

The runner skips tests with unresolved `FILL_FROM_` values. In practice, fill these manually after an initial run — look at the response from the dependency test and grab the real value.

## Writing good assertions

Assertions are the core of the eval. Each is a plain-English statement that's either true or false about the response.

### Programmatic assertions

These can be checked by code against the JSON response. Write them so the grading script can parse intent:

| Pattern | What the script checks |
|---------|----------------------|
| "Returns at least N results" | Array length >= N |
| "Returns N or fewer results" | Array length <= N |
| "Field X present" / "X visible" / "X included" | Key exists in response |
| "Each result has X" | Key exists on every array element |
| "Response bytes < N" | Raw response size |

**Good programmatic assertions:**
- "Returns at least one result"
- "Each contact has an ID"
- "Tags embedded in response"
- "Returns 3 or fewer projects"

### LLM-judgment assertions

These need a grader agent to evaluate. They cover semantic quality, usefulness, and fitness for purpose:

**Good judgment assertions:**
- "Response is useful for identifying sales opportunities"
- "Contact type (person vs organisation) is distinguishable"
- "Content volume assessment — how many tokens for an active contact?"

### Bad assertions

Avoid assertions that are:
- **Vague**: "Response looks correct" — correct how?
- **Untestable**: "Server performs well" — against what baseline?
- **Duplicative**: "Has ID" + "ID field present" + "Includes ID" — pick one
- **Implementation-specific**: "Returns JSON with key 'data.items[0].name'" — too brittle, breaks on minor schema changes

## Embed comparison pattern

To measure whether embed params are worth the token cost, create paired tests — same tool, different embeds:

```json
{
  "id": "read-4",
  "name": "projects-list",
  "tool": "list_projects",
  "params": {"embed": "tags,party", "perPage": "10"},
  "assertions": ["Tags included in response", "Linked parties visible"]
},
{
  "id": "read-4b",
  "name": "projects-minimal",
  "tool": "list_projects",
  "params": {"embed": "tags", "perPage": "3"},
  "assertions": ["Returns 3 or fewer projects", "Tags still present"]
}
```

The report compares token costs between these paired tests, showing whether full embeds are worth it.
