# ── Stage 1: build ───────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps before copying source for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

COPY . .

ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 2: serve ───────────────────────────────────────
FROM nginx:1.25-alpine AS runtime

LABEL org.opencontainers.image.title="real-time-inference/frontend" \
      org.opencontainers.image.description="React operator dashboard served by nginx"

# Replace default nginx config with one that proxies /api to the API service
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD wget -qO- http://localhost:80/ || exit 1
