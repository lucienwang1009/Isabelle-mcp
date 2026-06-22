#!/usr/bin/env bash
# Bootstrap a source checkout for local isabelle-mcp development.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/bootstrap.sh [--with-afp] [--afp-root PATH] [--afp-db PATH]

Options:
  --with-afp      Download/extract AFP sources and build the local AFP source index.
                  You can also set ISABELLE_MCP_BOOTSTRAP_AFP=1.
  --afp-root PATH Use an existing AFP root/thys directory and build the index only.
  --afp-db PATH   Override the AFP SQLite index path.
  -h, --help      Show this help.

Default: set up Python deps and run doctor without downloading AFP.
EOF
}

cd "$(dirname "$0")/.."

with_afp="${ISABELLE_MCP_BOOTSTRAP_AFP:-0}"
afp_root=""
afp_db=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-afp)
      with_afp=1
      shift
      ;;
    --afp-root)
      afp_root="${2:-}"
      if [[ -z "$afp_root" ]]; then
        echo "error: --afp-root requires a path" >&2
        exit 2
      fi
      shift 2
      ;;
    --afp-db)
      afp_db="${2:-}"
      if [[ -z "$afp_db" ]]; then
        echo "error: --afp-db requires a path" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

git submodule update --init --recursive
uv sync

if [[ -n "$afp_root" ]]; then
  args=(afp-index --afp-root "$afp_root")
  if [[ -n "$afp_db" ]]; then
    args+=(--db "$afp_db")
  fi
  uv run isabelle-mcp "${args[@]}"
elif [[ "$with_afp" == "1" || "$with_afp" == "true" || "$with_afp" == "yes" ]]; then
  args=(afp-bootstrap)
  if [[ -n "$afp_db" ]]; then
    args+=(--db "$afp_db")
  fi
  uv run isabelle-mcp "${args[@]}"
fi

uv run isabelle-mcp doctor
