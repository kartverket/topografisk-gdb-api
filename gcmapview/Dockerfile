# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY components ./components
COPY lib ./lib
COPY public ./public
COPY src ./src
COPY components.json index.html tsconfig.app.json tsconfig.json tsconfig.node.json vite.config.ts ./

RUN npm run build

FROM node:22-alpine AS runtime
RUN apk upgrade --no-cache
WORKDIR /app
COPY server.mjs /app/server.mjs
COPY --from=builder /app/dist /app/dist

EXPOSE 80
CMD ["node", "/app/server.mjs"]