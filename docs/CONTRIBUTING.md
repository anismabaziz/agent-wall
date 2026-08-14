# Contributing to AgentWall

## Workflow — commit to `main`

Trunk is **`main`** and stays green at all times. Work is committed **directly to
`main`** — one logical change per commit:

```bash
git checkout main && git pull
<make changes>
git add <files>
git commit -m "<one-sentence message>"
git push
```

Keep `main` green: run the checks locally before pushing (see below) so CI stays
green.

## Commit messages — one sentence

Write **a single concise sentence** that states what the commit does. One logical
change per commit; reference the issue number inline.

Good:

- `fix: enforce obligation fulfillment constraints`
- `feat: add agentwall CLI`
- `docs: document the LangGraph integration`

Avoid multi-paragraph bodies — the single sentence is the message.

Never commit secrets (`.env`) or the mutable DB (`agent_wall_audit.db`).

## Before you push

3. Run the checks locally and confirm everything passes before pushing:

   ```bash
   uv run python -m pytest -q
   uv run ruff check .
   uv run mypy .
   ```

## Resources

- [README](../README.md) — project overview and layout
- [api.md](api.md) — API usage notes
- Issue tracker: https://github.com/anismabaziz/agent-wall/issues
