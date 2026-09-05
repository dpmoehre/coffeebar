FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    COFFEEBAR_DATA=/data \
    PORT=8000
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY --from=web /web/dist ./web/dist
COPY scripts/start-cloud.sh ./scripts/start-cloud.sh
RUN chmod +x ./scripts/start-cloud.sh && mkdir -p /data
EXPOSE 8000
CMD ["./scripts/start-cloud.sh"]
