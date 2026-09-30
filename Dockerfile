FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
RUN useradd --create-home --uid 10001 queryotter
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY backend ./backend
COPY public ./public
RUN mkdir .data && chown -R queryotter:queryotter /app
USER queryotter
CMD ["uv", "run", "--no-sync", "python", "-m", "backend.cloud"]
