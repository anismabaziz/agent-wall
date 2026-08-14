# AgentWall — Roadmap to v1

Target: a usable, trustworthy, deployable v1 — fix everything that's broken,
close the correctness gaps, then harden the surface.

Each item links to its issue in [`issues.md`](./issues.md) and to its GitHub
issue and `phase:N` label. Items are ordered within each phase; phases should be
done in order.

Tracking: [open all issues](https://github.com/anismabaziz/agent-wall/issues) · filter by `phase:0` … `phase:5`.

Issue mapping (GitHub issue number = dev-guide issue number):
issues.md #1→#1, #2→#2, #3→#3, #4→#4, #5→#5, #6→#6, #7→#7, #8→#8, #9→#9,
#10→#10, #11→#11, #12→#12, #13→#13, #14→#14, #15→#15, #16→#16, #17→#17,
#18→#18, #19→#19/#20, #20→#20/#21.

---

## Phase 0 — Make the current state reproducible (do first)

1. **Recreate the virtualenv** — GitHub [#1](https://github.com/anismabaziz/agent-wall/issues/1) (+ `api.md` fix in [#2](https://github.com/anismabaziz/agent-wall/issues/2))
   - Delete `.venv`, run `uv venv && uv sync`, confirm `uv run uvicorn src.api:app` starts.
   - Verify `uv run python -m pytest -q` still gives 29 passing tests.
   - Update `api.md` to document `uv run python -m uvicorn src.api:app --reload`.
2. **Stop leaking secrets / mutable state** — GitHub [#9](https://github.com/anismabaziz/agent-wall/issues/9)
   - Add `.env` and `*.db` to `.gitignore`.
   - Rotate the `GROQ_API_KEY` in `.env` (it has been seen by the tooling).
   - Remove `agent_wall_audit.db` from git history (`git rm --cached` + history cleanup).
3. **Guard the test run** — GitHub [#18](https://github.com/anismabaziz/agent-wall/issues/18)
   - Add a `pytest.ini`/`pyproject` config so tests work regardless of CWD
     (set rootdir, or make policy/db paths absolute from the project root).
4. **Make audit DB path configurable** — GitHub [#11](https://github.com/anismabaziz/agent-wall/issues/11)
   - Accept a path via env var / constructor; keep a sensible default.

**Exit criteria:** fresh clone → `uv sync` → all tests pass → API starts with the
documented command; `git status` clean; no secrets in the repo.

---

## Phase 1 — Core correctness (the engine must be right)

5. **Wire the audit logger into the API's ObligationManager** — GitHub [#3](https://github.com/anismabaziz/agent-wall/issues/3)
   - Pass `audit_logger=audit_logger` in `src/api.py`.
6. **Enforce fulfillment constraints** — GitHub [#4](https://github.com/anismabaziz/agent-wall/issues/4)
   - `check_fulfillment()` must require `action.context` to satisfy the record's
     `fulfillment_constraint` (reuse the engine's constraint matcher).
   - Add tests: fulfillment with/without matching constraints.
7. **Implement `default_behavior` modes** — GitHub [#5](https://github.com/anismabaziz/agent-wall/issues/5)
   - `explicit_permit_implicit_prohibit` → current behavior (deny on no-match).
   - `explicit_permit_explicit_prohibit` → require explicit allow/deny lists;
     no-match falls back to a configurable default.
8. **Centralize obligation registration** — GitHub [#7](https://github.com/anismabaziz/agent-wall/issues/7)
   - Have the engine (or a small coordinator) register obligations from the
     verdict instead of each caller re-implementing the loop.
   - Surface the winning permission ID in the verdict and store it as
     `permission_id` (kill the `"unknown"` hardcode).
9. **Make `ObligationManager` thread-safe** — GitHub [#12](https://github.com/anismabaziz/agent-wall/issues/12)
   - Guard `_obligations` with a lock; update from both the API handlers and the
     polling task.

**Exit criteria:** new unit tests for 6–8 pass; audit log shows obligation events
from the REST API; obligation records carry real `permission_id`s.

---

## Phase 2 — Persistence (obligations must survive restarts)

10. **Persist obligations** — GitHub [#8](https://github.com/anismabaziz/agent-wall/issues/8)
    - Add an `obligations` table to the existing SQLite store (same engine as the
      audit log).
    - Load open records at startup; save on every state change
      (created/fulfilled/waived/violated).
    - Keep the deadline poller working against the persisted store.
11. **Backfill `/obligations` response** — GitHub [#17](https://github.com/anismabaziz/agent-wall/issues/17)
    - Return `permission_id` and `fulfillment_constraint`; add `limit`/`offset`.

**Exit criteria:** register an obligation → restart the server → it is still
`PENDING` with the original deadline; `/obligations` exposes full records.

---

## Phase 3 — Surface (CLI + LangGraph parity)

12. **Add a CLI** — GitHub [#13](https://github.com/anismabaziz/agent-wall/issues/13)
    - Add `[project.scripts]` entry (`agentwall = ...`) in `pyproject.toml`.
    - Commands: `evaluate` (policy + action → verdict), `obligations`,
      `audit-log`, `check` (validate a policy file).
13. **Unit-test the LangGraph enforcement node** — GitHub [#14](https://github.com/anismabaziz/agent-wall/issues/14)
    - Split `AgentWallToolNode` logic from the demo; test with a fake LLM/messages.
    - Keep `demo.py` as an opt-in live demo.
14. **Fix demo hygiene** — makes `demo.py` exit cleanly (it calls
    `obligation_manager.stop()` only on one path) and logs the audit summary.

**Exit criteria:** `agentwall evaluate ...` works from the shell; LangGraph
enforcement covered by deterministic tests; CI runs them.

---

## Phase 4 — Richer matching & policy surface

15. **Extend the constraint matcher** — GitHub [#15](https://github.com/anismabaziz/agent-wall/issues/15)
    - Support operators (`gt`, `lt`, `gte`, `lte`, `neq`, `in`, `contains`,
      wildcard `*` on strings), resource patterns, and subject scoping.
    - Keep backward compatibility with existing plain-equality policies.
16. **Define dispensation ordering** — GitHub [#16](https://github.com/anismabaziz/agent-wall/issues/16)
    - Document and enforce a deterministic order: dispensation → fulfillment →
      deadline, or make it explicit in the engine.
17. **Resolve the `derivations.py` placeholder** — GitHub [#6](https://github.com/anismabaziz/agent-wall/issues/6)
    - Either implement (derived permissions/obligations) or delete.

**Exit criteria:** new matcher features have tests; ordering documented; no empty
placeholder files.

---

## Phase 5 — Production hardening

18. **Secure the API** — GitHub [#10](https://github.com/anismabaziz/agent-wall/issues/10)
    - API key/auth middleware, rate limiting per subject, CORS config,
      pagination on `/obligations`.
19. **Add tooling & CI** — GitHub [#19](https://github.com/anismabaziz/agent-wall/issues/19)
    - `ruff` + `mypy` config in `pyproject.toml`, pre-commit hooks, GitHub Actions
      running lint + tests on every push.
20. **Fill in package metadata** — real description, version, `project.urls`,
    license in `pyproject.toml`.
21. **Document the LangGraph integration** — GitHub [#20](https://github.com/anismabaziz/agent-wall/issues/20)
    - README section for Extract-Evaluate-Apply, `AgentWallConfig`, and the
      builder; example of a custom context extractor.

**Exit criteria:** `pip install`-able package with a working `agentwall` command;
CI green; API protected; README covers REST + CLI + LangGraph.

---

## Suggested first session

1. Phase 0 — GitHub issues [#1](https://github.com/anismabaziz/agent-wall/issues/1), [#2](https://github.com/anismabaziz/agent-wall/issues/2), [#9](https://github.com/anismabaziz/agent-wall/issues/9), [#18](https://github.com/anismabaziz/agent-wall/issues/18) (fix the venv, gitignore, and CWD-independence) — these are small, safe, and unblock everyone.
2. Phase 1 — GitHub [#3](https://github.com/anismabaziz/agent-wall/issues/3) (wire the audit logger) — one line, immediately visible in `/audit-log`.
3. Phase 1 — GitHub [#4](https://github.com/anismabaziz/agent-wall/issues/4) (enforce fulfillment constraints) — the most important correctness gap.
