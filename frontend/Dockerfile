# Multi-stage build for Next.js Frontend
FROM node:20-alpine as base

# Install dependencies only when needed
FROM base as deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package files
COPY package*.json ./
# Copy lockfile if available
COPY package-lock.json* ./

# Install dependencies including dev deps (needed for build)
RUN npm ci

# Rebuild the source code only when needed
FROM base as builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Accept API base at build time (defaults to http://localhost:8000)
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
# Create environment file for build using the provided ARG
RUN echo "NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}" > .env.local

# Build the application (skip linting for Docker)
RUN npm run build -- --no-lint

# Production image, copy all the files and run next
FROM base as runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built application
COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
