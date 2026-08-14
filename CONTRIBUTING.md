# Contributing to AgentWall

## Branch naming convention

Trunk is **`main`** and stays green at all times. Work happens on **one branch
per roadmap phase**:

```
phase/0   phase/1   phase/2   phase/3   phase/4   phase/5
```

Each phase branch holds all the work for its associated issues (the `phase:N`
labels link issues to branches). Start a phase by switching to its branch:

```bash
git fetch origin
git checkout phase/N && git pull
```

All six phase branches already exist on the remote, branched from `main`. A
phase branch merges into `main` once every issue in that phase is done.

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

1. Pick an open issue, preferably one with an early `phase:` label
   (`phase:0` → `phase:5`).
2. Check out that phase's branch and implement the fix on it (see above).
3. Run the checks locally before pushing:

   ```bash
   uv run python -m pytest -q
   ```

4. Push and open a PR when the phase's work is ready:

   ```bash
   git push -u origin phase/N
   gh pr create --fill            # uses .github/PULL_REQUEST_TEMPLATE.md
   ```

5. Link and label the PR: add `Closes #<num>` to the body and the matching
   `phase:N` label. Ensure CI passes.
6. Squash-merge to `main` and delete the phase branch:

   ```bash
   gh pr merge --squash --delete-branch
   ```

`main` is branch-protected: it requires a pull request and a passing CI check
before merge.

## Resources

- **Phase runbook** (the end-to-end process we use for every phase): [`docs/phase-runbook.md`](docs/phase-runbook.md)
- Developer guide (issues, roadmap): [`dev-guide/`](dev-guide/) *(local only)*
- Full workflow details: [`dev-guide/workflow.md`](dev-guide/workflow.md)
- Issue tracker: https://github.com/anismabaziz/agent-wall/issues