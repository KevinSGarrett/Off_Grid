#!/usr/bin/env sh
set -eu

RUNTIME_DB_PATH="${RUNTIME_DB_PATH:-/app/data/private/offgrid.db}"
DEMO_SEED_DB="${DEMO_SEED_DB:-/app/data/demo_seed/offgrid_demo_seed.db}"
DEMO_RESET_ON_START="${DEMO_RESET_ON_START:-true}"
DEMO_MODE_NORMALIZED="$(printf '%s' "${DEMO_MODE:-true}" | tr '[:upper:]' '[:lower:]')"
RESET_NORMALIZED="$(printf '%s' "$DEMO_RESET_ON_START" | tr '[:upper:]' '[:lower:]')"

mkdir -p "$(dirname "$RUNTIME_DB_PATH")"

case "$DEMO_MODE_NORMALIZED" in
  1|true|yes|on)
    if [ ! -f "$DEMO_SEED_DB" ]; then
      echo "FATAL: demo mode requires deployment seed $DEMO_SEED_DB" >&2
      exit 72
    fi
    if [ "$RESET_NORMALIZED" = "1" ] || [ "$RESET_NORMALIZED" = "true" ] || [ "$RESET_NORMALIZED" = "yes" ] || [ "$RESET_NORMALIZED" = "on" ] || [ ! -f "$RUNTIME_DB_PATH" ]; then
      tmp="${RUNTIME_DB_PATH}.tmp"
      cp "$DEMO_SEED_DB" "$tmp"
      mv "$tmp" "$RUNTIME_DB_PATH"
    fi
    ;;
esac

exec "$@"
