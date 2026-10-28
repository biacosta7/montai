#!/usr/bin/env bash
# Envia o último commit para o Hugging Face Space.
#
# O Space precisa de um README com metadados YAML no topo; o do GitHub não tem.
# Este script monta uma cópia dos arquivos versionados (git archive, então .env
# e secrets nunca vão junto), troca o README pelo space/README.md e sobe tudo.
#
# Uso: space/deploy.sh <usuario>/<nome-do-space>
set -euo pipefail

space="${1:?uso: space/deploy.sh <usuario>/<nome-do-space>}"
root="$(git rev-parse --show-toplevel)"
cd "$root"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Há mudanças não commitadas; o deploy usa só o último commit." >&2
fi

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

git archive HEAD | tar -x -C "$stage"
cp space/README.md "$stage/README.md"
rm -rf "$stage/space" "$stage/.claude"

# --delete "*" apaga do Space o que saiu do repositório (o .gitattributes fica).
hf upload "$space" "$stage" . --repo-type space --delete "*" \
  --commit-message "Deploy $(git rev-parse --short HEAD)"
