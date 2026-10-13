#!/usr/bin/env bash
# Backup do Postgres de produção: pg_dump no formato custom (comprimido), com rotação.
#
#   scripts/backup-db.sh [--no-rotate]
#
# Grava BACKUP_DIR/receita-<data UTC>.dump e apaga os com mais de BACKUP_KEEP_DAYS dias
# (as duas do .env.production; padrão /var/backups/receita e 14). O dump é conferido com
# pg_restore --list antes de entrar na pasta. Restaure com scripts/restore-db.sh.
# --no-rotate: não apaga nada (é o que o restore-db.sh usa no backup de segurança).
# Cron (todo dia às 03:15): veja docs/DEPLOY.md, "Backups".
set -euo pipefail

rotate=1
for arg in "$@"; do
  case "$arg" in
    --no-rotate) rotate=0 ;;
    *)
      echo "uso: scripts/backup-db.sh [--no-rotate]" >&2
      exit 1
      ;;
  esac
done

# shellcheck source=scripts/_compose.sh
source "$(dirname "${BASH_SOURCE[0]}")/_compose.sh"

BACKUP_DIR=${BACKUP_DIR:-$(env_value BACKUP_DIR)}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/receita}
BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS:-$(env_value BACKUP_KEEP_DAYS)}
BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}

umask 077
mkdir -p "$BACKUP_DIR"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/receita-$stamp.dump"
partial="$BACKUP_DIR/.receita-$stamp.dump.partial"
trap 'rm -f "$partial"' EXIT

log "backup do banco para $target"
compose exec -T db pg_dump -U receita -d receita --format=custom --compress=9 --no-owner \
  >"$partial"
# Um dump truncado (disco cheio, container reiniciado) falha aqui e não substitui nada.
compose exec -T db pg_restore --list <"$partial" >/dev/null
mv "$partial" "$target"
log "ok: $(du -h "$target" | cut -f1)"

if [[ "$rotate" -eq 0 ]]; then
  exit 0
fi
removed=$(find "$BACKUP_DIR" -maxdepth 1 -name 'receita-*.dump' -mtime +"$BACKUP_KEEP_DAYS" -print -delete | wc -l)
if [[ "$removed" -gt 0 ]]; then
  log "rotação: $removed backup(s) com mais de $BACKUP_KEEP_DAYS dias apagado(s)"
fi
