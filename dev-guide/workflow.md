# AgentWall — Contribution & Branching Workflow

The single author should be able to move fast AND keep `main` always green.
Rule of thumb: **trunk-based development — one short-lived branch per GitHub issue,
merged back to `main` with a PR.**

## Branching model

| What | Convention |
|---|---|
| Trunk | `main` — always passing, shippable |
| One branch per issue | `<phase>#<num>-<slug>` e.g. `phase0/#1-fix-venv`, `phase1/#4-fulfillment-constraints` |
| Docs-only / tiny fixes | `docs/<slug>` or `chore/<slug>`; optionally bundle a few small issues in one branch |
| Lifecycle | create → push → open PR to `main` → merge → delete branch |

- Generate a branch straight from an issue:
  ```bash
  gh issue develop <num> --checkout          # creates phase0/#<num>-<slug> from main
  gh issue develop 9 --checkout --branch-name phase0/#9-ignore-secrets
  ```
- The `phase:N` labels already govern ordering — do not keep longer-lived
  `phase/N` branches. Merge each issue as soon as it's green.

## Before you start

- Start from an up-to-date `main`: `git fetch origin && git checkout main && git pull`
- Refresh `main` protection status: `gh repo view --json branchProtection` (optional)

## Commit guidelines

- One logical change per commit; reference the issue: `#7: centralize obligation registration`
- Never commit secrets (`.env`) or the mutable DB (`agent_wall_audit.db`).
- Prefer conventional prefixes: `fix:`, `feat:`, `docs:`, `chore:`, `test:`,
  `refactor:`, `security:`.

## Opening a PR

```bash
git push -u origin <branch>
gh pr create --fill                 # uses the PR template below
gh pr ready                         # mark ready for review once checks pass
```

- The PR template lives at `.github/PULL_REQUEST_TEMPLATE.md` and is auto-filled.
- Link the issue with `Closes #<num>` so merging auto-closes it.
- Add/label the PR with the matching `phase:N` label.

## Merging

- `main` requires a pull request (with at least one approving review if a second
  set of eyes exists) and passing CI checks before merge.
- Prefer **Squash and merge** to keep `main` history clean.
- Delete the branch after merge (`gh pr merge --delete-branch --squash`).

## Releasing / milestones

- Tag phases in **milestones**, not branches: `v0.2`, `v1.0`.
- When all phase issues are closed, cut a tag (`git tag v0.1.0 && git push --tags`)
  and Draft a GitHub Release.

## Quick references

- Issues: https://github.com/anismabaziz/agent-wall/issues
- Labels: `bug`, `enhancement`, `security`, `docs`, `good-first-issue`, `phase:0`–`phase:5`