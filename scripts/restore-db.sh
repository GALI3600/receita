#!/usr/bin/env bash
# Restaura um backup feito por scripts/backup-db.sh, SUBSTITUINDO o banco atual.
#
#   scripts/restore-db.sh /var/backups/receita/receita-20260101T031500Z.dump [--yes]
#
# 1. faz um backup do banco atual (rede de segurança, na mesma pasta dos backups);
# 2. para a API e os workers (o site continua no ar, mas a API responde 502);
# 3. recria o banco e aplica o dump;
# 4. sobe tudo de novo (o migrate leva um backup antigo até a versão atual do schema).
set -euo pipefail
# shellcheck source=scripts/_compose.sh
source "$(dirname "${BASH_SOURCE[0]}")/_compose.sh"

dump=${1:-}
if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "uso: scripts/restore-db.sh <arquivo .dump> [--yes]" >&2
  exit 1
fi

compose exec -T db pg_restore --list <"$dump" >/dev/null || {
  echo "erro: $dump não é um dump válido do pg_dump (formato custom)" >&2
  exit 1
}

if [[ "${2:-}" != "--yes" ]]; then
  read -r -p "Isto apaga o banco atual e restaura $dump. Digite 'restaurar' para continuar: " answer
  [[ "$answer" == "restaurar" ]] || { echo "cancelado"; exit 1; }
fi

log "backup de segurança do banco atual"
"$ROOT_DIR/scripts/backup-db.sh"

log "parando API e workers"
compose stop api worker worker-whisper

log "recriando o banco"
compose exec -T db psql -U receita -d postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE IF EXISTS receita WITH (FORCE)' \
  -c 'CREATE DATABASE receita OWNER receita'

log "restaurando $dump"
compose exec -T db pg_restore -U receita -d receita --no-owner --exit-on-error <"$dump"

log "subindo o stack (migrate, API e workers)"
compose up -d --wait

log "restauração concluída"
