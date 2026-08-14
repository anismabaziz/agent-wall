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
# 1. Install dependencies
uv sync

# 2. Run the test suite (29 tests)
uv run python -m pytest -q

# 3. Start the API server
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
curl "http://localhost:8000/obligations?status=PENDING"   # list obligations
curl "http://localhost:8000/audit-log?limit=100"          # audit trail
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

```python
from integrations.langgraph.builder import build_agent_wall_agent

app = build_agent_wall_agent(
    tools=tools,
    llm=llm_with_tools,          # ChatGroq etc.
    policy_engine=policy_engine,
    obligation_manager=obligation_manager,
    audit_logger=audit_logger,
    config=config,
    checkpointer=MemorySaver(),
)
```

See `integrations/langgraph/demo.py` for a runnable financial-services demo (requires a `GROQ_API_KEY`).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, commit message
style (one sentence), and how to work on an issue.

Want the exact end-to-end process we use to ship each roadmap phase (branch →
commit → verify → PR tagging its issues → merge)? See
[`docs/phase-runbook.md`](docs/phase-runbook.md).

## Project layout

```
src/
  models.py        Pydantic data models + YAML policy loader
  engine.py        PolicyEngine — match rules, resolve conflicts, produce Verdict
  conflict.py      ConflictResolver — RulePriority lookups
  obligations.py   ObligationManager — register / fulfill / waive / violate + deadline polling
  audit.py         AuditLogger — SQLAlchemy + SQLite audit store
  api.py           FastAPI service
  derivations.py   (placeholder — not yet implemented)
integrations/
  langgraph/       Extract-Evaluate-Apply tool node + agent builder + demo
policies/          Example YAML policy sets
scenarios/         JSON end-to-end scenarios
tests/             Pytest suite (29 tests)
main.py            CLI stub (not yet implemented)
api.md             API usage notes
```

## Status

Core engine, obligation lifecycle, audit logging, REST API, and LangGraph integration are implemented and tested.

- Known issues & gaps: [`dev-guide/issues.md`](dev-guide/issues.md)
- Roadmap to v1 (with GitHub issue links): [`dev-guide/roadmap-to-v1.md`](dev-guide/roadmap-to-v1.md)
- Issue tracker (open / planned work, tagged by `phase:0`–`phase:5`): https://github.com/anismabaziz/agent-wall/issues
