FROM node:24-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

ARG VITE_API_BASE_URL
ARG VITE_AUTH_MODE=disabled
ARG VITE_GCIP_API_KEY
ARG VITE_GCIP_AUTH_DOMAIN
ARG VITE_GCIP_PROJECT_ID

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE
ENV VITE_GCIP_API_KEY=$VITE_GCIP_API_KEY
ENV VITE_GCIP_AUTH_DOMAIN=$VITE_GCIP_AUTH_DOMAIN
ENV VITE_GCIP_PROJECT_ID=$VITE_GCIP_PROJECT_ID

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
