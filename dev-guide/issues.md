# AgentWall — Known Issues: Missing Things & Things That Don't Work

Audit performed 2026-08-14. All findings verified against the current codebase
(tests pass, 29/29; API verified manually).

Legend: **BROKEN** = actively fails today · **MISSING** = never implemented · **RISK** = latent problem

---

## 1. BROKEN — Broken virtualenv: console scripts point at a dead interpreter

`.venv` was copied from another project (`obligo`). Every console script
(`.venv/bin/uvicorn`, `.venv/bin/pytest`, …) has a stale shebang:

```
#!/Users/abaziz/Documents/programming/portfolio-projects/obligo/.venv/bin/python3
```

That path does not exist, so `uv run uvicorn src.api:app` fails with
`ModuleNotFoundError: No module named 'fastapi'` and `uv run pytest` fails with
`bad interpreter`. `uv sync` re-audits packages but does **not** rewrite the
shebangs.

**Workaround** (works today): always use module form:
`uv run python -m uvicorn ...` and `uv run python -m pytest`.

**Fix**: delete `.venv` and recreate it in this directory (`uv venv && uv sync`),
then verify `uv run uvicorn src.api:app` starts. Add `.venv` recreation to the
dev setup docs.

---

## 2. BROKEN / CONFUSING — `api.md` documents the wrong module and command

`api.md:3` says `uvicorn agent_wall.api:app --reload`:

- The package is named `src`, not `agent_wall` (`src/api.py`), so this command
  fails even with a working console script.
- Combined with issue #1, the documented quick-start is broken end to end.

**Fix**: document `uv run python -m uvicorn src.api:app --reload`.

---

## 3. BROKEN — Obligations are not audited through the REST API

`src/api.py:22` constructs `ObligationManager(poll_interval_seconds=10)` **without**
`audit_logger=...`. As a result, when obligations are created/fulfilled/waived/
violated via the HTTP service, no audit entries are written. The LangGraph
integration and the tests do pass the logger, so behavior is inconsistent across
entry points.

**Fix**: `ObligationManager(poll_interval_seconds=10, audit_logger=audit_logger)`
in `src/api.py`.

---

## 4. MISSING — Fulfillment constraints are parsed but never enforced

`ObligationRecord.fulfillment_constraint` is stored (from `action.context`), and
`ObligationManager.register()` accepts it, but `check_fulfillment()` only matches
on `subject` + `action_type`. Verified: an obligation registered with
`fulfillment_constraint={'requires_note': True}` is marked FULFILLED by an action
with an empty context. Constraints must be checked before fulfilling.

---

## 5. MISSING — `default_behavior` is dead configuration

`PolicySet.default_behavior` accepts two modes, but `PolicyEngine` never reads it.
`explicit_permit_explicit_prohibit` mode has no implementation; the engine always
returns `DEFAULT_DENY` on no-match regardless of the configured mode.

---

## 6. MISSING — `src/derivations.py` is an empty placeholder

Zero lines of code. Either implement or remove; nothing references it.

---

## 7. MISSING — Obligation registration logic is duplicated and fragile

The engine returns obligation IDs in the verdict, but does not register them.
Three call sites each reimplement the lookup + `register()` loop:
`src/api.py:58-70`, `integrations/langgraph/tool_node.py:156-188`, and
`tests/test_scenarios.py:37-49`. All hardcode `permission_id="unknown"` (the
winning permission ID is known to the engine but never surfaced). Centralize this
in the engine (or a coordinator) and return the permission ID in the verdict.

---

## 8. MISSING — Obligations are in-memory only

`ObligationManager._obligations` is a plain dict. Restarting the server loses all
pending obligations, so a 15-day CTR deadline disappears on the first deploy.
Audit data is persisted (SQLite) but the obligations themselves are not. This
blocks any real-world use where obligations outlive a process.

---

## 9. RISK — Secrets committed / not ignored

- `.env` contains a real `GROQ_API_KEY` and is **not** in `.gitignore`. It is
  currently untracked (good) but one `git add .` commits it.
- `agent_wall_audit.db` **is** committed to git and keeps changing on every
  evaluation. Committing a mutable SQLite database pollutes history and can leak
  production-like audit data.

**Fix**: add `.env` and `*.db` (or the db file) to `.gitignore`; rotate the Groq
key; consider removing the db from history.

---

## 10. MISSING — No auth, rate limiting, or CORS on the API

`/evaluate` can be called by anyone. No authentication, no per-subject quotas, no
CORS config for browser-based UIs, no pagination on `/obligations` (only
`/audit-log` supports limit/offset).

---

## 11. RISK — Audit DB path is hardcoded and CWD-dependent

`src/audit.py:33` creates the engine at module import time against
`sqlite:///agent_wall_audit.db` (relative path). The DB lands wherever the process
started, and the path cannot be configured. Make the DB path configurable
(env var / constructor) and resolve it relative to a stable location.

---

## 12. RISK — `ObligationManager` is not thread-safe

The same dict is mutated from FastAPI async handlers (`/evaluate`) and from the
background deadline-polling task (`start()`/`start_polling()`), with no locks.
FastAPI runs handlers on a thread pool, so concurrent `/evaluate` calls can
interleave writes to `_obligations`.

---

## 13. BROKEN — `main.py` is a stub and there is no CLI

`main.py` just prints `"Hello from agent-wall!"`. There is no way to evaluate an
action, check obligations, or inspect the audit log from the command line without
starting the server. A small CLI (`agentwall evaluate --policy ... --action ...`)
is the natural v1 deliverable.

---

## 14. MISSING — LangGraph demo depends on a live LLM

`integrations/langgraph/demo.py` requires a valid `GROQ_API_KEY` and network
access to run, so it cannot be exercised in CI or offline. The enforcement logic
(`tool_node.py`) has no unit tests at all — it's only exercised by running the
demo. Split the enforcement logic from the demo and unit-test it with a fake LLM.

---

## 15. MISSING — Engine matching is too rigid (equality only)

`PolicyEngine._matches` requires strict equality on every constraint key. No
support for ranges (`amount > 10000`), inequality, wildcards, list membership,
subject scoping (`subject == "payments_agent_1"`), or resource pattern matching
(`transaction://*`). Real policies need these.

---

## 16. MISSING — No dispensation ordering guarantee

Dispensation is checked after the obligation is registered (api.py), which works
only because waivers target `PENDING` records. There is no defined order or
guarantee between dispensation, fulfillment, and deadline checks when multiple
events arrive together.

---

## 17. MISSING — `/obligations` response omits fields

`fulfillment_constraint` and `permission_id` exist on the record but are not
returned by `src/api.py:92-106`. Consumers can't tell *why* an obligation exists
or what would fulfill it.

---

## 18. RISK — Relative imports make tests CWD-dependent

Tests import `src.models` and load `policies/...` / `scenarios/...` by relative
path, so they only pass when run from the repo root. This is fine for `uv run`
but fragile for CI runners that cd elsewhere first.

---

## 19. MISSING — No tooling hygiene

- No linter/formatter config (ruff/mypy/black) in `pyproject.toml`.
- No CI pipeline.
- No `[project.scripts]` entry point in `pyproject.toml` (nothing installs an
  `agentwall` command).
- `pyproject.toml` description is the default `"Add your description here"`.

---

## 20. MISSING — No docs for the LangGraph integration

`README.md` (previously empty) and `api.md` cover the REST API only. The
Extract-Evaluate-Apply contract, `AgentWallConfig`, `AgentWallToolNode`, and
`build_agent_wall_agent()` are undocumented outside source comments.
