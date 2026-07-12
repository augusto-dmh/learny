# Learny frontend image — multi-stage (AD-042).
#
# Targets:
#   - `prod`: builds the Next.js app and runs the standalone server (`node
#     server.js`) as a non-root user. Selected by docker-compose.prod.yml.
#   - `dev` (default/last stage): the Next dev server, used by the local base
#     compose (`docker compose up`), which sets no build target.

# --- deps: install from the committed lockfile (reproducible) ------------------
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- build: produce the standalone production bundle ---------------------------
FROM node:20-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# --- prod: run the built standalone server as non-root -------------------------
FROM node:20-slim AS prod
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN useradd --system --uid 1001 --create-home nextjs
# The standalone output bundles a minimal server + its node_modules; static
# assets must be copied alongside it.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]

# --- dev (default): the Next dev server for local Docker Compose ---------------
FROM node:20-slim AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
