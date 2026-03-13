# ============================================================
# Stage 1 — Builder
# ============================================================
FROM node:22-slim AS builder

WORKDIR /build

# Install dependencies first (layer cache optimisation).
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

# Copy source and compile TypeScript.
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# ============================================================
# Stage 2 — Runtime (minimal, non-root)
# ============================================================
FROM node:22-slim AS runtime

# Install curl for HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user.
RUN groupadd -r datamind && useradd -r -g datamind -s /sbin/nologin datamind

# Copy compiled output and production dependencies.
COPY --from=builder /build/dist ./dist
COPY --from=builder /build/node_modules ./node_modules
COPY package.json ./

# Lock down ownership.
RUN chown -R datamind:datamind /app

USER datamind

EXPOSE 8070

HEALTHCHECK --interval=20s --timeout=10s --retries=5 --start-period=15s \
    CMD curl -f http://localhost:8070/health/liveness || exit 1

ENV PORT=8070
ENV LOG_LEVEL=info

CMD ["node", "dist/index.js"]
