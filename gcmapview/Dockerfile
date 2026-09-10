# syntax=docker/dockerfile:1

FROM node:26-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY components ./components
COPY lib ./lib
COPY public ./public
COPY src ./src
COPY components.json index.html tsconfig.app.json tsconfig.json tsconfig.node.json vite.config.ts ./

RUN npm run build

FROM builder AS runtime-dependencies
RUN npm prune --omit=dev

FROM node:26-alpine AS runtime
WORKDIR /app
COPY --from=runtime-dependencies /app/node_modules /app/node_modules
RUN apk upgrade --no-cache \
 && rm -rf /usr/local/lib/node_modules/npm \
 && rm -f /usr/local/bin/npm /usr/local/bin/npx
COPY server.mjs /app/server.mjs
COPY --from=builder /app/dist /app/dist

EXPOSE 8080
CMD ["node", "/app/server.mjs"]