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

FROM nginx:1.29-alpine AS runtime
RUN apk upgrade --no-cache
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY runtime-config.js.template /opt/gcmapview/runtime-config.js.template
COPY docker-entrypoint.d/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]