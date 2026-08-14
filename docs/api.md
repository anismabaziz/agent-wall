# AgentWall REST API

A deontic policy firewall for agentic AI. You submit an agent's proposed
action (who wants to do what, to which resource, under what context) and the
API returns a verdict: **PERMIT** or **DENY**, why, and any obligations that
must be met for the action to proceed.

## Quick start

```bash
# 1. Install dependencies
uv sync --extra dev

# 2. Start the server (auto-reload enabled)
uv run python -m uvicorn src.api:app --reload
```

The API listens at `http://localhost:8000`. An **interactive OpenAPI/Swagger
UI** is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Configuration

All settings are optional and read from environment variables:

| Variable                | Default  | Purpose                                            |
| ----------------------- | -------- | -------------------------------------------------- |
| `AGENT_WALL_API_KEY`    | *(off)*  | When set, every request must send `X-API-Key`.     |
| `AGENT_WALL_RATE_LIMIT` | `1000`   | Max `/evaluate` requests per subject per 60s. `0` disables. |
| `AGENT_WALL_CORS_ORIGINS` | `*`    | Comma-separated allowed origins.                  |

```bash
AGENT_WALL_API_KEY=secret AGENT_WALL_RATE_LIMIT=60 \
  uv run python -m uvicorn src.api:app --reload
```

## Authentication

Keyed requests must include the `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret" \
  -d '{ ... }'
```

Failing or omitting the key when one is configured returns `401`.

---

## Endpoints

### `POST /evaluate`

Evaluate an agent action against the policy set.

**Request body**

| Field         | Type     | Required | Description                              |
| ------------- | -------- | -------- | ---------------------------------------- |
| `subject`     | `string` | yes      | Identity of the acting agent.            |
| `action_type` | `string` | yes      | The action being attempted (e.g. `execute_payment`). |
| `resource`    | `string` | yes      | Target resource (e.g. `transaction://high-value-001`). |
| `context`     | `object` | no       | Extra facts the rules may match on.      |

**Response** (`200`)

| Field        | Type     | Description                                    |
| ------------ | -------- | ---------------------------------------------- |
| `decision`   | `string` | `PERMIT` or `DENY`.                            |
| `explanation`| `string` | Human-readable reason, including rule resolution. |
| `obligations`| `string[]` | Obligation IDs to fulfill if permitted.   |

**Example**

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "payments_agent_1",
    "action_type": "execute_payment",
    "resource": "transaction://high-value-001",
    "context": {
      "is_high_value": true,
      "has_treasury_approval": true
    }
  }'
```

```json
{
  "decision": "PERMIT",
  "explanation": "Resolved by RulePriority Priority_ApprovalOverProh: Perm_ApprovedHighValue outranks conflicting prohibition(s)",
  "obligations": ["Ob_FileCTR"]
}
```

**Error codes**

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| `401`| Missing / invalid API key.                        |
| `422`| Invalid or incomplete request body.               |
| `429`| Per-subject rate limit exceeded.                  |

---

### `GET /obligations`

List registered obligation records with optional filters.

**Query params**

| Param    | Type     | Default | Description                          |
| -------- | -------- | ------- | ------------------------------------ |
| `status` | `string` | *(all)* | `PENDING`, `FULFILLED`, `VIOLATED`, or `WAIVED`. |
| `limit`  | `int`    | `100`   | Max rows (1–1000).                   |
| `offset` | `int`    | `0`     | Row to start from.                   |

**Example**

```bash
curl "http://localhost:8000/obligations?status=PENDING"
```

Returns an array of obligation records; each includes `id`, `obligation_id`,
`permission_id`, `subject`, `obliged_action`, `deadline`, `status`,
`fulfillment_constraint`, and the fulfillment / violation / waiver timestamps.

---

### `GET /audit-log`

Return recent decision audit entries.

**Query params**

| Param    | Type  | Default | Description        |
| -------- | ----- | ------- | ------------------ |
| `limit`  | `int` | `100`   | Max rows (1–1000). |
| `offset` | `int` | `0`     | Row to start from. |

**Example**

```bash
curl "http://localhost:8000/audit-log?limit=50"
```

```json
[
  {
    "id": 1,
    "timestamp": "2026-08-14T22:40:03.123456",
    "action": "payments_agent_1 execute_payment transaction://high-value-001",
    "verdict": "PERMIT",
    "explanation": "Resolved by RulePriority ...",
    "matched_rules": "Perm_ApprovedHighValue",
    "obligation_change": "Ob_FileCTR: registered"
  }
]
```

---

## Room tour

1. **Two terminals**: keep the server running in one, fire requests in the
   other.
2. Start with the **flagship scenario** above — it exercises rule-priority
   conflict resolution and triggers an obligation (`Ob_FileCTR`).
3. Confirm the decision was audited:
   ```bash
   curl http://localhost:8000/audit-log
   ```
4. Confirm the obligation was registered as pending:
   ```bash
   curl "http://localhost:8000/obligations?status=PENDING"
   ```