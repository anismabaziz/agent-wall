"""agent-wall console entry point.

Thin wrapper around the CLI implementation in :mod:`src.cli`. The console
script `agentwall` (see pyproject.toml) points at `src.cli:main`.
"""
from src.cli import main


if __name__ == "__main__":
	raise SystemExit(main())