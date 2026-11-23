# Built from the repo root: docker build -f services/main-worker/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PORT=8080

WORKDIR /app
COPY libs/shared ./libs/shared
COPY services/main-worker ./services/main-worker

# --no-sources: install the local paths given here instead of resolving the workspace.
RUN uv pip install --system --no-cache --no-sources ./libs/shared ./services/main-worker

RUN useradd --system --uid 10001 --no-create-home app
USER app

CMD ["sh", "-c", "exec uvicorn main_worker.main:app --host 0.0.0.0 --port ${PORT}"]
