# Recruiter-friendly one-command run: no Python or uv needed on the host.
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY integrations/ ./integrations/
COPY policies/ ./policies/
COPY main.py ./

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
