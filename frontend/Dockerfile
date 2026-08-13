# MIDIgen Studio — Next.js 15 (standalone)
# Build: docker build --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 -t midigen-frontend ./frontend
FROM node:22-bookworm-slim AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Ensure public/ exists (repo may not ship static assets yet)
RUN mkdir -p public \
    && npm run build:prod

FROM node:22-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3001 \
    HOSTNAME=0.0.0.0

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin midigen

COPY --from=builder /app/public ./public
COPY --from=builder --chown=midigen:midigen /app/.next/standalone ./
COPY --from=builder --chown=midigen:midigen /app/.next/static ./.next/static

USER midigen

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3001').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
