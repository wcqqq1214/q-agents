# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS base

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app/frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
