# AgentWall architecture

A technical walkthrough of how AgentWall works, aimed at engineers who need to
read, extend, or operate the code. It covers the domain model, the decision
engine, the obligation lifecycle, persistence, the API, the LangGraph
integration, and the CLI. Where a behavior is subtle, the doc says so and
points at the file and function that owns it.

## Concepts and terminology

AgentWall is a decision point for AI agents. Before an agent acts, it asks
AgentWall whether the action is allowed. The vocabulary is borrowed from
deontic logic:

- Subject. The identity of the acting agent, for example `payments_agent_1`.
- Action type. What the agent is trying to do, for example `execute_payment`.
- Resource. What the action targets, for example `transaction://high-value-001`.
- Context. Extra facts that rules can match against, such as
  `is_high_value: true`. This is free-form and application-specific.
- Permission. A rule that permits an action when its constraints are met.
- Prohibition. A rule that blocks an action when its constraints are met.
- Obligation. A conditional duty that is attached to a permission. An agent may
  be allowed to do X only if it later does Y.
- Dispensation. A waiver. It forgives a pending obligation in advance.
- Verdict. The result of evaluating one action: permit, prohibit, or default
  deny, plus the reason and any obligations.

The four concepts fit into one request model:

```python
class Action(BaseModel):
    subject: str
    action_type: str
    resource: str
    context: Dict[str, Any]
```

## Policy file format

A policy is YAML loaded into a `PolicySet` via `load_policy()` in
`src/models.py`. `PolicySet` is a Pydantic model, so the file is validated at
load time and a bad file fails fast.

The composite example (`policies/p5_composite.yaml`) shows every construct,
now using the type-reasoning and credential-gate forms:

```yaml
ontology:
  - id: Transaction
    subClassOf: []
  - id: HighValueTransaction
    subClassOf: [Transaction]
  - id: CrossBorderTransfer
    subClassOf: [HighValueTransaction]

credential_authorities:
  - TreasuryAuthority

permissions:
  - id: Perm_ApprovedHighValue
    action: execute_payment
    constraint:
      matches_type: HighValueTransaction
      credential: TreasuryAuthority
    provisions:
      - Ob_FileCTR

prohibitions:
  - id: Proh_AutoHighValue
    action: execute_payment
    constraint:
      matches_type: HighValueTransaction

obligations:
  - id: Ob_FileCTR
    obliged_action: file_ctr
    deadline_minutes: 21600

dispensations:
  - id: Disp_ExemptCTR
    constraint:
      is_exempt_counterparty: true
    waives: Ob_FileCTR

rule_priorities:
  - id: Priority_ApprovalOverProh
    greater: Perm_ApprovedHighValue
    lesser: Proh_AutoHighValue

default_behavior: explicit_permit_implicit_prohibit
```

Two policy semantics are supported by `default_behavior`:

- `explicit_permit_implicit_prohibit` (default). If nothing matches, deny.
- `explicit_permit_explicit_prohibit`. If nothing matches, fall back to
  `default_decision`, which is `DENY`, `PERMIT`, or `PROHIBIT`.

## The decision engine

The engine lives in `src/engine.py`, class `PolicyEngine`. Its public entry
point is `evaluate(action) -> Verdict`, which wraps the private `_evaluate` in
a safety net. If `_evaluate` raises for any reason, `evaluate` returns a
`DEFAULT_DENY` verdict and logs it. The engine favors failing closed.

### Rule matching

For each rule, `_matches(action, rule)` decides whether it applies:

1. The rule's `action` must equal the request's `action_type`.
2. Every key in the rule's `constraint` must resolve. `subject` and `resource`
   are read from the action; any other key must exist in `action.context`.
   A missing context key causes the rule to not match.
3. Each constraint value is compared to the actual value with
   `operator_match`.

`operator_match` (also in `src/engine.py`) supports several comparisons:

- A plain scalar compares for equality (`is_high_value: true`).
- A string containing `*` is a wildcard glob via `fnmatch`,
  so `transaction://*` matches any transaction URL.
- An operator dict maps to more precise comparisons:
  `gt`, `lt`, `gte`, `lte`, `neq`, `in`, `contains`, and `wildcard`.
  Range operators coerce both sides to numbers and refuse to match when either
  side is not numeric.

Two special constraint keys leave the decision to the machine rather than the
model:

- `matches_type` reasons over a small type ontology (`PolicySet.ontology`). It
  is satisfied when any of the action's `_resource_types` is a member of the
  named class or one of its subclasses. Because matching follows the subclass
  closure, a rule over `HighValueTransaction` automatically covers
  `CrossBorderTransfer` and any subclass added later — the rule itself does not
  change.
- `credential` gates on a verified pass. It is satisfied only when the action's
  `_credential_issuer` is present and listed in `PolicySet.credential_authorities`.
  An absent or untrusted issuer is treated as no approval (deny).

### Decision matrix

Provided permission and prohibition lists are gathered, the engine applies the
following rules in order:

| Permissions | Prohibitions | Result |
| --- | --- | --- |
| yes | no | `PERMIT` |
| no | yes | `PROHIBIT` |
| yes | yes | conflict, resolved by priority (below) |
| no | no | default behavior |

### Conflict resolution

When at least one permission and one prohibition both match, the engine asks
`ConflictResolver` (`src/conflict.py`) whether any `RulePriority` relationship
settles it. A priority is a pair: `greater` names the rule that wins, `lesser`
the rule that loses. The resolver holds a lookup map built from those pairs and
checks every permission/prohibition combination in both directions.

- If a permission outranks a prohibition, the verdict is `PERMIT`, and only the
  winning permission's obligations are considered.
- If a prohibition outranks a permission, the verdict is `PROHIBIT`.
- If no priority covers the pair, the conflict is unresolved and the verdict is
  `DEFAULT_DENY`.

### Derived obligations

Obligations are declared once in the policy and referenced by permissions
through `provisions`. `src/derivations.py` computes the set of obligations that
a set of permissions provisions. Because it returns a deduplicated set, the same
obligation provisioned by several permissions is only reported once. The engine
uses this to attach obligations to `PERMIT` verdicts.

## Obligation lifecycle

Obligations move through four states, modeled as `ObligationStatus` in
`src/models.py`: `PENDING`, `FULFILLED`, `VIOLATED`, `WAIVED`.

`ObligationManager` (`src/obligations.py`) owns the lifecycle in memory and can
mirror it to a store. Registration happens through `register()`, which builds a
record with a composite id of the obligation, the timestamp, and the subject.
The `deadline` is computed as now plus `deadline_minutes`.

Key operations:

- `check_fulfillment(action)`. An action that matches a pending obligation's
  `obliged_action`, `subject`, and `fulfillment_constraint` flips that record to
  `FULFILLED` and stamps `fulfilled_at`.
- `_check_deadlines()`. Any `PENDING` record past its deadline becomes
  `VIOLATED`. This runs continuously from a background asyncio task started in
  the FastAPI lifespan.
- `check_dispensation(action, dispensations)`. A dispensation whose constraint
  matches the context waives the named pending obligation, recording who waived
  it and when.
- `enforce(action, ...)`. This is the deterministic event ordering that a
single action triggers, executed under one lock so the order is atomic to
concurrent events: first dispensation, then fulfillment, then deadline
checks. Consumers never depend on registration order.

The lock is a re-entrant lock, so nested calls from `enforce` into the check
helpers do not deadlock.

## Persistence

State is stored in SQLite through SQLAlchemy. `src/db.py` builds the engine and
the shared session factory. The database path defaults to
`agent_wall_audit.db` at the repository root and can be overridden with
`AGENT_WALL_AUDIT_DB`.

Two tables are registered on the shared `Base`:

- `audit_log`, mapped by `AuditEntry` in `src/audit.py`.
- `obligations`, mapped by `ObligationEntry` in `src/obligation_store.py`.

`ObligationStore` is the persistence boundary for obligations. Its `save()`
upserts a record (insert when new, update mutable fields when present), and
`load_all()` reads every row back into domain objects. The fulfillment
constraint is serialized to JSON for storage and deserialized on load. The store
can also be constructed with an explicit path, which tests use to isolate the
database.

The audit store (`AuditLogger`) writes a row per decision via `log_decision()`
and per obligation lifecycle event via `log_obligation()`. It does not store the
request context, only the subject, action, resource, verdict, explanation,
matched rule ids, and any obligation change.

## API layer

`src/api.py` exposes the system over HTTP with FastAPI. The application is fast
about being stateless at the edges but holds three long-lived singletons: the
loaded `policy`, the `PolicyEngine`, and the `ObligationManager`.

Endpoints:

- `POST /evaluate`. Takes an `EvaluateRequest`, runs the engine, registers any
  produced obligations, calls `enforce()` for the deterministic post-action
  ordering, and returns a verdict.
- `GET /obligations`. Lists obligation records, filterable by `status` and
  paginated with `limit` and `offset`.
- `GET /audit-log`. Lists recent audit entries, newest first, paginated.

Hardening controls, all configurable through environment variables:

- Authentication. When `AGENT_WALL_API_KEY` is set, protected routes and the
  interactive schema require the `X-API-Key` header. The comparison uses
  `hmac.compare_digest` to avoid leaking the key through timing. `evaluate` is
  additionally rate limited per subject.
- Rate limiting. `AGENT_WALL_RATE_LIMIT` caps `/evaluate` requests per subject
  per minute using a sliding-window limiter (`src/rate_limit.py`). A limit of
  `0` disables it.
- Body size. `AGENT_WALL_MAX_BODY_BYTES` (default 1 MiB) caps request body
  size. A middleware returns `413` for oversized bodies, including chunked
  frames.
- CORS. `AGENT_WALL_CORS_ORIGINS` is a comma-separated allow list that defaults
  to any origin with credentials disabled.
- Schema privacy. When a key is configured, `/docs`, `/redoc`, and
  `/openapi.json` require the key too.

## LangGraph integration

The integration under `integrations/langgraph/` makes enforcement part of an
agent's tool boundary rather than a separate call. It implements an
Extract, Evaluate, Apply loop:

- Extract. `normalize_tool_call()` in `extract.py` turns a raw LangGraph tool
  call into an `Action`. The subject comes from `default_subject` (or the
  configured agent id), the action type is the tool name, and a resource is
  heuristically picked from common argument fields such as `path`, `url`, or
  `document_id`. If none are found, a short hash of the arguments becomes the
  resource. Context is assembled from the tool arguments plus the thread id and
  a message count.
- Evaluate. The normalized action runs through `PolicyEngine.evaluate()`.
- Apply. `AgentWallToolNode` (`tool_node.py`) executes the tool only on a
  `PERMIT` verdict, registers the verdict's obligations, and checks whether the
  action fulfilled any pending obligation. On `PROHIBIT` or `DEFAULT_DENY` it
  returns a `ToolMessage` stating the policy violation instead of running the
  tool.

`builder.py` provides `build_agent_wall_agent()`, which wires the node into the
standard LangGraph ReAct pattern: an agent node that calls the LLM, a
conditional edge to the policy-aware tool node, and a checkpointer for
persistence.

This substitution is what turns AgentWall from an API you call into a guardrail
the agent has to pass through before any tool runs.

## CLI

`src/cli.py` is a small command-line mirror of the API for local use. It exposes
subcommands for `evaluate`, `obligations`, `audit-log`, and check helpers. The
evaluate subcommand accepts a policy, subject, action, resource, and repeated
`--context KEY=VALUE` flags, and prints the same verdict the API would return.

## Concurrency

Three independent concurrency concerns coincide:

- The obligation manager guards its in-memory registry with a re-entrant lock.
- The rate limiter guards its timestamp deques with a standard lock.
- Deadline polling runs as an asyncio background task started in the FastAPI
  lifespan, cancelled on shutdown.

Because the request handlers are async but the engine and manager work is
synchronous, FastAPI runs that work on the thread pool. The locks above keep the
shared state safe across those workers.

## Threading through a request

1. The agent submits an `Action` over HTTP to `/evaluate` (or through the
   LangGraph tool node).
2. The engine matchers evaluate every permission and prohibition.
3. The decision matrix and, when needed, the conflict resolver produce a
   `Verdict`.
4. A permit with obligations registers records via the manager and persists
   them.
5. The manager runs `enforce()` to apply dispensation, fulfillment, and
   deadline effects deterministically.
6. The decision and any obligation events are written to the audit log.
7. The verdict returns to the caller; the agent acts only if it was permitted.

## Source layout

```
src/
  models.py            Domain models, policy loading, verdict
  engine.py            PolicyEngine, rule matching, decision matrix
  conflict.py          ConflictResolver and rule priorities
  derivations.py       Derived / deduplicated obligation resolution
  obligations.py       ObligationManager and lifecycle
  obligation_store.py  SQLAlchemy persistence for obligations
  audit.py             AuditLogger and audit_log table
  db.py                SQLAlchemy engine, session, Base
  rate_limit.py        Sliding-window rate limiter
  api.py               FastAPI application and hardening controls
  cli.py               Command-line interface
integrations/
  langgraph/
    config.py          AgentWallConfig typed dict
    extract.py         Extract step (tool call -> Action)
    tool_node.py       Apply step (policy-aware tool execution)
    builder.py         ReAct graph wiring
    demo.py            Runnable payments demo (requires GROQ_API_KEY)
policies/              Example YAML policy sets
tests/                 Pytest suite
```

## Verifying a change

```bash
uv run python -m pytest -q     # unit + API + integration tests
uv run ruff check src/ integrations/
uv run mypy src/ integrations/
```

## Machine-determined authorization

Decision enforcement is deterministic and lives outside the LLM; the engine
defaults to deny on any internal error. Two mechanisms close the gaps that would
otherwise let a model assert its own authorization:

- **Type reasoning.** "Is this high value?" is a *type*, decided by subclass
  reasoning over `PolicySet.ontology`, not a flag the model writes. A rule over
  `HighValueTransaction` uses `matches_type` and automatically covers
  `CrossBorderTransfer` and any future subclass, so new domain types are covered
  without editing rules.
- **Credential-gated approval.** Approval is a pass whose issuer must be in
  `PolicySet.credential_authorities` (`credential` constraint). A missing or
  untrusted issuer means no approval. The model presents the pass; it does not
  decide whether it is valid.

In the LangGraph integration the extractor stages only operator-owned facts into
the reserved context keys `_resource_types` and `_credential_issuer`
(`resource_classifier` and `credential_resolver` in `AgentWallConfig`). Raw model
tool arguments are inert report data; the model cannot reach those reserved keys.

Where each concept lives:

| Concept | AgentWall |
| --- | --- |
| Permission / Prohibition | `PolicySet.permissions` / `.prohibitions` |
| Rule priority | `PolicySet.rule_priorities` |
| Obligation + provision | `Obligation` + `Permission.provisions` |
| Dispensation | `PolicySet.dispensations` |
| Default behavior | `default_behavior` |
| Extract–Evaluate–Apply | `extract.py` → `engine.py` → `tool_node.py` |
| class ontology + subclass reasoning | `PolicySet.ontology` + `matches_type` |
| trusted-issuer credential check | `credential_authorities` + `credential` |
| structured, requested-attribute-only audit | `audit_log` incl. `policy_version` hash |

The `policies/p5_composite.yaml` flagship policy demonstrates the pathway: a
high-value typed payment is prohibited without a treasury credential, and
permitted (filing a CTR obligation) with one.