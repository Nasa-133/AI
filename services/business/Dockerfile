# Build context: repo ildizi. docker build -f services/business/Dockerfile .
# Repo tuzilmasi image ichida takrorlanadi, shuning uchun uv.lock o‘zgarishsiz (--frozen) ishlaydi.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/abo_messaging /repo/packages/abo_messaging
WORKDIR /repo/services/business
COPY services/business/pyproject.toml services/business/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/business/src ./src
COPY services/business/migrations ./migrations
COPY services/business/alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable
RUN useradd --create-home app
USER app
ENV PATH="/repo/services/business/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "business.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
