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

# Roda sem root (uid 10002). Os certificados e o estado ficam em /data e /config (volumes, do
# usuário caddy); o site em /srv continua do root, só para leitura do processo. As portas 80/443
# abrem pelo sysctl net.ipv4.ip_unprivileged_port_start do docker-compose.prod.yml, então o
# binário perde a file capability (cap_net_bind_service): com cap_drop ALL, o exec de um binário
# com capability que o container não tem falha com "operation not permitted". A cópia não leva
# o xattr.
RUN cp /usr/bin/caddy /tmp/caddy && mv -f /tmp/caddy /usr/bin/caddy \
    && addgroup -S -g 10002 caddy \
    && adduser -S -D -H -h /data -s /sbin/nologin -u 10002 -G caddy caddy \
    && chown -R caddy:caddy /data /config
COPY --from=build /app/dist /srv
USER caddy
