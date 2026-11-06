#!/usr/bin/env bash
set -euo pipefail

owner='user-bcp-student41'
repo='hackaton-grupo-08'
engine='auto'
while [ "$#" -gt 0 ]; do
  case "$1" in
    --owner|--repo|--engine)
      [ "$#" -ge 2 ] || { printf 'Falta el valor de %s\n' "$1" >&2; exit 2; }
      case "$1" in --owner) owner=$2;; --repo) repo=$2;; --engine) engine=$2;; esac
      shift 2;;
    --help)
      printf 'Uso: bash start-mcp.sh [--owner user-bcp-student41] [--repo hackaton-grupo-08] [--engine auto|podman|docker]\n'
      exit 0;;
    *) printf 'Opción desconocida: %s\n' "$1" >&2; exit 2;;
  esac
done
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || { printf 'Owner de GitHub inválido.\n' >&2; exit 2; }
[[ "$repo" =~ ^[A-Za-z0-9._-]+$ ]] || { printf 'Nombre de repositorio inválido.\n' >&2; exit 2; }
case "$engine" in
  auto)
    if command -v podman >/dev/null 2>&1; then engine='podman';
    elif command -v docker >/dev/null 2>&1; then engine='docker';
    else printf 'Instala Podman o Docker antes de iniciar MCP.\n' >&2; exit 1; fi;;
  podman|docker) command -v "$engine" >/dev/null || { printf 'No se encuentra %s.\n' "$engine" >&2; exit 1; };;
  *) printf 'Motor inválido: %s\n' "$engine" >&2; exit 2;;
esac
command -v gh >/dev/null || { printf 'Instala GitHub CLI y ejecuta gh auth login.\n' >&2; exit 1; }
LAB4_GITHUB_TOKEN=$(gh auth token)
[ -n "$LAB4_GITHUB_TOKEN" ] || { printf 'Ejecuta gh auth login antes de levantar MCP.\n' >&2; exit 1; }
export GITHUB_TOKEN="$LAB4_GITHUB_TOKEN" GITHUB_OWNER="$owner" GITHUB_REPO="$repo"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
printf 'MCP local con %s para %s/%s. GitHub Projects: 8083; GitHub Tasks: 8081.\n' "$engine" "$owner" "$repo"
"$engine" build -f Dockerfile -t localhost/mcp-local_github-project:latest .
"$engine" build -f Dockerfile -t localhost/mcp-local_github-task:latest .
if [ "$engine" = 'podman' ]; then exec podman compose --in-pod false up;
else exec docker compose up; fi
