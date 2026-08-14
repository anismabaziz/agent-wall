# Phase Runbook — how we ship a phase

This is the step-by-step process used to deliver **Phase 0** (issues #1, #2, #9,
#18, #11). Every roadmap phase (0→5) follows the same drill:

> branch-per-phase → one commit per issue → verify → push → PR that tags its
> issues → merge → issues auto-close.

The roadmap lives at [`dev-guide/roadmap-to-v1.md`](../dev-guide/roadmap-to-v1.md)
(local-only) and on the GitHub issue tracker
(<https://github.com/anismabaziz/agent-wall/issues>). Each issue carries a
`phase:N` label linking it to its phase branch.

Follow `CONTRIBUTING.md` for contribution conventions
(<https://github.com/anismabaziz/agent-wall/blob/main/CONTRIBUTING.md>).

---

## 1. Set up the phase branch

All six phase branches (`phase/0` … `phase/5`) already exist on the remote,
branched from `main`.

```bash
git fetch origin
git checkout phase/N && git pull
```

Start clean — confirm nothing unexpected is on the branch:

```bash
git status --short
git log --oneline -5
```

**Note on repo hygiene:** `dev-guide/` is `gitignore`d (local only). If you are a
new clone, ignore it; the source of truth for issues is GitHub.

---

## 2. Inventory the phase's issues

Pull the issue numbers and `phase:N` labels for the phase:

```bash
gh label list
gh issue list --label "phase:0" --state open
```

For phase 0 these were:

> **#1** Broken virtualenv · **#2** api.md wrong command · **#9** secrets/mutable DB ·
> **#18** tests CWD-dependent · **#11** audit DB path

Order them by dependency/biggest risk first (e.g. secrets and environment before
test hardening). One commit per issue keeps history reviewable and lets each
issue be closed individually on merge.

---

## 3. Solve each issue and commit

For each issue, in order:

1. Read the affected files and reproduce the problem.
2. Apply the smallest fix that resolves it.
3. **Verify** the fix (tests, server boot, curl, console output).
4. Commit **only that issue's files** with a one-sentence message referencing the
   issue:

   ```bash
   git add <files>
   git commit -m "<type>: <what it does> (#<num>)"
   ```

   Conventional types: `fix:`, `feat:`, `chore:`, `test:`, `docs:`, `security:`.

### Real phase/0 commits (as examples)

```
fix: recreate venv and correct API run command (#1, #2)
chore: stop tracking mutable audit DB and secrets (#9)
test: make tests CWD-independent (#18)
feat: make audit DB path configurable via env var (#11)
```

**Do** commit only the issue's own files — keep unrelated local leftovers out
(e.g. `src/derivations.py`, a placeholder for issue #6, stays untracked).

---

## 4. Final verification before opening the PR

Run the whole suite exactly as CI will:

```bash
uv run python -m pytest -q     # must be green (currently 29 tests)
```

Sanity-check the last issue if it changed runtime behavior (e.g. server boots,
an endpoint responds):

```bash
uv run python -m uvicorn src.api:app --port 8000   # in another terminal
curl -X POST http://localhost:8000/evaluate -H "Content-Type: application/json" \
  -d '{"subject":"payments_agent_1","action_type":"execute_payment","resource":"transaction://high-value-001","context":{"is_high_value":true,"has_treasury_approval":true}}'
```

Review the exact diff going into the PR:

```bash
git log --oneline main..phase/N
git status --short
```

---

## 5. Push and open the PR — tag the issues it solves

```bash
git push -u origin phase/N
```

Create the PR from the phase branch to `main`, with a body that **explicitly
lists every issue it closes** so merging auto-closes them:

```bash
gh pr create --repo anismabaziz/agent-wall --base main --head phase/N \
  --title "<Phase N>: <short summary>" \
  --label "phase:N" \
  --body @pr-body.md
```

The PR body must contain, one per line:

```
Closes #<num>
```

for **every** issue the phase solves, plus:

- Summary of what the phase delivers
- Type-of-change checklist (the `.github/PULL_REQUEST_TEMPLATE.md` model)
- The commit list
- Verification / logs
- Review notes (e.g. "#9: rotate GROQ_API_KEY separately — out of repo scope")

### Real phase/0 PR

> PR **#21** — "Phase 0: environment, secrets, test & audit hardening"
>
> `Closes #1`, `Closes #2`, `Closes #9`, `Closes #18`, `Closes #11`

---

## 6. Watch the checks, then merge

Confirm CI is green on the PR (branch protection requires it to merge to `main`):

```bash
gh pr checks <N>               # poll until 'test' => pass
gh pr view <N>
```

Merge as a squash to keep `main` history clean. Deleting the branch auto-closes
the linked issues:

```bash
gh pr merge <N> --squash --delete-branch
```

After merge:

```bash
git checkout main && git pull
git fetch --prune origin                    # drop the deleted phase branch
```

Verify all tagged issues are now closed:

```bash
gh issue list --label "phase:N" --state open    # should be empty
```

---

## 7. Do the env-level follow-ups

Some issue fixes are *environmental* and can't be captured in a commit or PR:

- **Rotating secrets** — `GROQ_API_KEY` sits in `.env`, now gitignored, but the
  key should be **rotated** in the provider dashboard (can't be done from the
  repo).
- Any manual config required on the remote (branch protection, default branch,
  labels) that was done once during setup.

Do these as soon as the PR merges so the issue is genuinely "done", not just
"code merged".

---

## Full flow at a glance

```
issue list (label phase:N)         ─┐
checkout phase/N                    │
foreach issue: solve → verify →    │  per phase
   commit one-sentence (#<num>)     │
uv run python -m pytest -q          │
git push -u origin phase/N          │
gh pr create (Closes #.. per issue) ─┘
gh pr checks -> wait 'test' pass    ─┐
gh pr merge --squash --delete-branch│  close loop
verify issues closed; rotate secrets┘
```

Repeat for `phase/1` … `phase/5` per [`dev-guide/roadmap-to-v1.md`](../dev-guide/roadmap-to-v1.md).