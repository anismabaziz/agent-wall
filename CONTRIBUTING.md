# Contributing to AgentWall

## Branch naming convention

Trunk is **`main`** and stays green at all times. Work happens on **one branch
per feature**:

```
feature/<feature-id>
```

Each feature branch holds all the work for its associated issues (the `feature:N`
labels link issues to branches). Start a feature by switching to its branch:

```bash
git fetch origin
git checkout feature/<feature-id> && git pull
```

Feature branches are branched from `main`. A feature branch merges into `main`
once every issue in that feature is done.

## Commit messages — one sentence

Write **a single concise sentence** that states what the commit does. One logical
change per commit; reference the issue number inline.

Good:

- `fix: enforce obligation fulfillment constraints`
- `feat: add agentwall CLI (#13)`
- `docs: document the LangGraph integration (#20)`

Avoid multi-paragraph bodies — the single sentence is the message.

Never commit secrets (`.env`) or the mutable DB (`agent_wall_audit.db`).

## How to continue / work on an issue

1. Pick an open issue, preferably one with an early `feature:` label.
2. Check out that feature's branch and implement the fix on it (see above).
3. Run the checks locally before pushing:

   ```bash
   uv run python -m pytest -q
   ```

4. Push and open a PR when the feature's work is ready:

   ```bash
   git push -u origin feature/<feature-id>
   gh pr create --fill            # uses .github/PULL_REQUEST_TEMPLATE.md
   ```

5. Link and label the PR: add `Closes #<num>` to the body and the matching
   `feature:N` label. Ensure CI passes.
6. Squash-merge to `main` and delete the feature branch:

   ```bash
   gh pr merge --squash --delete-branch
   ```

`main` is branch-protected: it requires a pull request and a passing CI check
before merge.

## Resources

- **Feature runbook** (the end-to-end process for shipping a feature branch):
  [`docs/phase-runbook.md`](docs/phase-runbook.md)
- Developer guide (issues, roadmap): [`dev-guide/`](dev-guide/) *(local only)*
- Full workflow details: [`dev-guide/workflow.md`](dev-guide/workflow.md)
- Issue tracker: https://github.com/anismabaziz/agent-wall/issues
