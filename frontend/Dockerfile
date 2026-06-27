# Learny frontend image — Next.js dev server for the Cycle-1 scaffold.
# A production multi-stage build (next build/start) lands with VPS hardening.
FROM node:20-slim

WORKDIR /app

# Install deps from the committed lockfile (reproducible).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
