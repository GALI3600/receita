# syntax=docker/dockerfile:1

# Alvos:
#   dev   — docker-compose.yml: servidor do Vite (src/ e index.html montados por bind mount);
#   prod  — docker-compose.prod.yml (o padrão): o build estático servido pelo Caddy, que também
#           faz o HTTPS e o proxy de /api para a API. O Caddyfile vem de deploy/Caddyfile.

# --- dev --------------------------------------------------------------------------------------
FROM node:22-alpine AS dev

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]

# --- build estático ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# Chave pública do Cloudflare Turnstile, embutida no JS no build; vazia, sem captcha.
ARG VITE_TURNSTILE_SITE_KEY=""
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN npm run build

# --- prod: Caddy com o dist -------------------------------------------------------------------
FROM caddy:2-alpine AS prod

COPY --from=build /app/dist /srv
