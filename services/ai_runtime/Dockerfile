# Build context: repo ildizi. docker build -f services/ai_runtime/Dockerfile .
# Repo tuzilmasi image ichida takrorlanadi, shuning uchun uv.lock o‘zgarishsiz (--frozen) ishlaydi.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/abo_messaging /repo/packages/abo_messaging
WORKDIR /repo/services/ai_runtime
COPY services/ai_runtime/pyproject.toml services/ai_runtime/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/ai_runtime/src ./src
COPY services/ai_runtime/migrations ./migrations
COPY services/ai_runtime/alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable
RUN useradd --create-home app
USER app
ENV PATH="/repo/services/ai_runtime/.venv/bin:$PATH"
EXPOSE 8100
# Worker: python -m ai_runtime.bootstrap.worker
CMD ["uvicorn", "ai_runtime.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
