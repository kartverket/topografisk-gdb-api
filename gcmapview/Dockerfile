# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder
WORKDIR /app

ARG VITE_GEOCOMPONENTS_API_URL=/geocomponents-api
ARG VITE_GCIMPORT_API_URL=/gcimport-api
ENV VITE_GEOCOMPONENTS_API_URL=$VITE_GEOCOMPONENTS_API_URL
ENV VITE_GCIMPORT_API_URL=$VITE_GCIMPORT_API_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY components ./components
COPY lib ./lib
COPY public ./public
COPY src ./src
COPY components.json index.html tsconfig.app.json tsconfig.json tsconfig.node.json vite.config.ts ./

RUN npm run build

FROM nginx:1.29-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]