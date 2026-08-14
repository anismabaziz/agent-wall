# AgentWall

**Deontic Policy Firewall for Agentic AI**

AgentWall is a guardrail layer that sits between an AI agent and its tool-calling layer. Every action an agent proposes (e.g. `execute_payment`, `export_dataset`) is checked against a declarative policy written in YAML before it is allowed to run. The engine returns one of three verdicts:

- **PERMIT** — the action is explicitly allowed (possibly with attached *obligations*)
- **PROHIBIT** — the action is explicitly blocked
- **DEFAULT_DENY** — nothing matched, so it is refused (fail-closed)

Beyond simple allow/deny, AgentWall models deontic concepts used in real-world compliance:

| Concept | Meaning | Example |
|---|---|---|
| **Permission** | An action that is allowed when its constraints match | `execute_payment` when `is_high_value: true` **and** `has_treasury_approval: true` |
| **Prohibition** | An action that is blocked when its constraints match | `execute_payment` when `is_high_value: true` |
| **Obligation** | A duty that must be performed after a permitted action, with a deadline | File a CTR with FinCEN within 15 days |
| **Dispensation** | A waiver that cancels an obligation when its constraints match | Counterparty is exempt → no CTR needed |
| **RulePriority** | Resolves *permission vs prohibition* conflicts | Approved high-value payment outranks the auto-prohibition |
| **Default behavior** | Fail-open vs fail-closed mode (fail-closed by default) | `explicit_permit_implicit_prohibit` |

Every decision and every obligation lifecycle event (created / fulfilled / violated / waived) is written to an append-only audit log (SQLite), so agent behavior is fully explainable and reviewable.

## Architecture

```
        agent  ──proposes action (subject, action_type, resource, context)──▶  AgentWall
                                                                                │
                        ┌─────────────────────────────┐                         │
                        │         PolicyEngine        │  match permissions /    │
                        │   src/engine.py             │  prohibitions, resolve  │
                        │   + src/conflict.py         │  conflicts              │
                        └──────────────┬──────────────┘                         │
                                       │ verdict (PERMIT/PROHIBIT/DEFAULT_DENY)  │
                                       ▼                                         │
                        ┌─────────────────────────────┐                         │
                        │      ObligationManager      │  register, fulfill,     │
                        │   src/obligations.py        │  waive, violate (timer)  │
                        └──────────────┬──────────────┘                         │
                                       ▼                                         │
                        ┌─────────────────────────────┐                         │
                        │         AuditLogger         │  every decision +        │
                        │   src/audit.py  (SQLite)    │  obligation event        │
                        └─────────────────────────────┘                         │
                                                                                ▼
                                        execute tool   (PERMIT)   /   return violation   (deny)
```

Three entry points share the same core engine:

1. **REST API** (`src/api.py`, FastAPI) — standalone service with `/evaluate`, `/obligations`, `/audit-log` endpoints.
2. **LangGraph integration** (`integrations/langgraph/`) — a drop-in `AgentWallToolNode` replacement for LangGraph's `ToolNode` that extracts → evaluates → applies every tool call, plus a `build_agent_wall_agent()` helper.
3. **Library / tests** — the engine, obligation manager, and audit logger are plain Python classes usable directly.

## Quick start

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies (incl. dev/lint tools)
uv sync --dev

# 2. Run the test suite
uv run python -m pytest -q

# 3. Lint and type-check
uv run ruff check .
uv run mypy src integrations

# 4. Start the API server
uv run python -m uvicorn src.api:app --reload
```

### Example: evaluate an action

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "payments_agent_1",
    "action_type": "execute_payment",
    "resource": "transaction://high-value-001",
    "context": {"is_high_value": true, "has_treasury_approval": true}
  }'
```

Response:

```json
{
  "decision": "PERMIT",
  "explanation": "Resolved by RulePriority Priority_ApprovalOverProh: Perm_ApprovedHighValue outranks conflicting prohibition(s)",
  "obligations": ["Ob_FileCTR"]
}
```

### Other endpoints

```bash
curl "http://localhost:8000/obligations?status=PENDING"       # list obligations (limit/offset supported)
curl "http://localhost:8000/audit-log?limit=100&offset=0"     # audit trail
```

### API security (optional)

All optional; all are disabled/unrestricted by default:

| Env var | Effect |
|---|---|
| `AGENT_WALL_API_KEY` | When set, every endpoint requires an `X-API-Key: <key>` header (otherwise `401`). |
| `AGENT_WALL_RATE_LIMIT` | Max `/evaluate` calls per subject per minute (default `1000`; `0` disables). |
| `AGENT_WALL_CORS_ORIGINS` | Comma-separated allowed origins (default `*`). |

```bash
AGENT_WALL_API_KEY=dev-key \
AGENT_WALL_RATE_LIMIT=120 \
AGENT_WALL_CORS_ORIGINS=http://localhost:5173 \
  uv run python -m uvicorn src.api:app --reload

# then
curl -H "X-API-Key: dev-key" http://localhost:8000/obligations
```

## Policies

Policies are YAML files in `policies/`:

- `p1_basic.yaml` — permit / prohibit basics
- `p2_obligation.yaml` — obligations with deadlines
- `p3_conflict.yaml`, `p4_tiebreak.yaml` — rule-priority conflict resolution
- `p4_dispensation.yaml` — dispensation / waiver flow
- `p6_shared_obligation.yaml` — one obligation provisioned by multiple permissions
- `p5_composite.yaml` — flagship financial-services policy (high-value payment + CTR obligation + dispensation + priority)

End-to-end scenarios live in `scenarios/` and are exercised by the parametrized test `tests/test_scenarios.py`.

## LangGraph integration

AgentWall plugs into a LangGraph agent at the **tool boundary** so every tool call is checked against policy before it executes, exactly like the REST `/evaluate` endpoint — but inline in the graph.

### The Extract–Evaluate–Apply contract

Every tool the model proposes goes through three steps:

| Step | Responsibility | Where |
|---|---|---|
| **Extract** | Map a raw tool call (`name`, `args`) into a normalized `Action` (subject, action_type, resource, context) | `normalize_tool_call()` in `integrations/langgraph/extract.py` |
| **Evaluate** | Run the `Action` through `PolicyEngine.evaluate()` → `PERMIT` / `PROHIBIT` / `DEFAULT_DENY` | `src/engine.py` |
| **Apply** | `PERMIT` → invoke the tool and register obligations; otherwise return a policy-violation `ToolMessage` | `AgentWallToolNode` in `integrations/langgraph/tool_node.py` |

```python
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from src.models import load_policy
from src.audit import AuditLogger
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from integrations.langgraph.builder import build_agent_wall_agent
from integrations.langgraph.config import AgentWallConfig

@tool
def execute_payment(amount: float, recipient: str) -> str:
    """Execute a payment to a recipient."""
    return f"Paid {amount} to {recipient}"

tools = [execute_payment]

policy = load_policy("policies/p5_composite.yaml")
audit_logger = AuditLogger(policy_file="p5_composite.yaml")
policy_engine = PolicyEngine(policy, audit_logger=audit_logger)
obligation_manager = ObligationManager(poll_interval_seconds=10, audit_logger=audit_logger)

config = AgentWallConfig(
    policy_file="p5_composite.yaml",
    default_subject="payments_agent_1",
)

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0).bind_tools(tools)

app = build_agent_wall_agent(
    tools=tools,
    llm=llm,
    policy_engine=policy_engine,
    obligation_manager=obligation_manager,
    audit_logger=audit_logger,
    config=config,
    checkpointer=MemorySaver(),
)
```

### `AgentWallConfig`

A `TypedDict` controlling extraction. All keys are optional:

| Key | Type | Meaning |
|---|---|---|
| `policy_file` | `str` | Policy name for audit attribution |
| `audit_db_path` | `str` | Override the SQLite audit/obligation DB path |
| `obligation_poll_interval` | `int` | Seconds between deadline checks |
| `default_subject` | `str` | Subject used when a tool call has no agent id |
| `context_extractors` | `dict[str, Callable]` | Per-tool functions that enrich the `Action` context before evaluation |

These correspond to the keys read by `build_agent_wall_agent` and `AgentWallToolNode`.

### `AgentWallToolNode`

A drop-in replacement for LangGraph's built-in `ToolNode`. You normally don't construct it directly — `build_agent_wall_agent` does — but it can be used on its own when you want the enforcement at a specific node:

```python
from integrations.langgraph.tool_node import AgentWallToolNode

node = AgentWallToolNode(
    tools=tools,
    policy_engine=policy_engine,
    obligation_manager=obligation_manager,
    audit_logger=audit_logger,
    config=config,
)
```

### Using a custom context extractor

Some policies need facts that aren't in the tool arguments. Register a per-tool extractor that reads the graph state and injects extra context:

```python
def enrich_with_state(tool_name, tool_input, state):
    # Pull an approval flag from the agent/thread metadata.
    return {"has_treasury_approval": state["configurable"]["approved"]}

config = AgentWallConfig(
    default_subject="payments_agent_1",
    context_extractors={"execute_payment": enrich_with_state},
)
```

The extracted keys are merged into the `Action.context` and matched against the policy's permission/prohibition constraints (see [Policies](#policies)).

See `integrations/langgraph/demo.py` for a runnable financial-services demo (requires a `GROQ_API_KEY`; it exits cleanly even on error).

## Contributing

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the commit-to-`main`
workflow and commit message style (one sentence).

## Project layout

```
src/
  models.py        Pydantic data models + YAML policy loader
  engine.py        PolicyEngine — match rules, resolve conflicts, produce Verdict
  conflict.py      ConflictResolver — RulePriority lookups
  obligations.py   ObligationManager — register / fulfill / waive / violate + deadline polling
  audit.py         AuditLogger — SQLAlchemy + SQLite audit store
  api.py           FastAPI service
  derivations.py   Derived policy evaluation
integrations/
  langgraph/       Extract-Evaluate-Apply tool node + agent builder + demo
policies/          Example YAML policy sets
scenarios/         JSON end-to-end scenarios
tests/             Pytest suite
main.py            CLI entry point
docs/
  api.md           API usage notes
  CONTRIBUTING.md  Contributing guide
```

## Status

Core engine, obligation lifecycle, audit logging, REST API, and LangGraph integration are implemented and tested.

- Issue tracker (open / planned work): https://github.com/anismabaziz/agent-wall/issues
