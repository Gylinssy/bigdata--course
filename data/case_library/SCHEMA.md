# Structured Case Schema

Each line in `structured_cases.jsonl` must be a single JSON object and include:

- `case_id` (string, unique)
- `title` (string)
- `domain` (string)
- `summary` (string)
- `outcome` (`success` / `failed` / `pivot`)
- `failure_reasons` (string array)
- `lessons` (string array)
- `key_metrics` (object)

Recommended optional fields:

- `stage`
- `source`
- `year`
- `tags`

## Quality Gates

Before appending new cases:

1. Field completeness >= 95%.
2. No duplicate `case_id`.
3. At least one metric in `key_metrics`.
4. `summary` should include user/problem/solution/result in 3-6 sentences.
5. Each case should have at least one actionable lesson.
