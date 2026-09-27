# Build context: repo ildizi. docker build -f services/integration_runtime/Dockerfile .
# Repo tuzilmasi image ichida takrorlanadi, shuning uchun uv.lock o‘zgarishsiz (--frozen) ishlaydi.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/abo_messaging /repo/packages/abo_messaging
WORKDIR /repo/services/integration_runtime
COPY services/integration_runtime/pyproject.toml services/integration_runtime/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/integration_runtime/src ./src
COPY services/integration_runtime/migrations ./migrations
COPY services/integration_runtime/alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable
# DEMO connector uchun sintetik ma’lumot (haqiqiy ERP emas).
COPY fixtures/synthetic/demo /repo/fixtures/synthetic/demo
ENV INTEGRATION_DEMO_DATA_DIR=/repo/fixtures/synthetic/demo
RUN useradd --create-home app
USER app
ENV PATH="/repo/services/integration_runtime/.venv/bin:$PATH"
EXPOSE 8200
CMD ["uvicorn", "integration_runtime.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8200"]
