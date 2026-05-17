#!/usr/bin/env bash
# Guard against shipping internal / dev-only URLs in public plugin packages.
#
# Allowed production hosts:
#   - https://daslrxpkbkqrbnjwouiq.supabase.co/functions/v1/  (active, canonical)
#   - https://api.nakopay.com/v1/                             (reserved fallback,
#                                                              declared in plugin
#                                                              clients for future
#                                                              self-hosted cutover)
#   - nakopay.com / *.nakopay.com docs + marketing links
#
# What we DO want to catch:
#   - localhost / 127.0.0.1 hardcoded base URLs
#   - lovable.app / lovable.dev preview URLs (transient sandboxes)
#   - any *.supabase.co project ref OTHER than the canonical one above
#
# Usage: plugins/scripts/check-no-internal-urls.sh [path...]
#   - paths default to the directory containing this script's parent (plugins/)
#   - exits 0 on clean, non-zero on the first leak
set -euo pipefail

if [[ $# -gt 0 ]]; then
  ROOTS=("$@")
else
  ROOTS=("$(cd "$(dirname "$0")/.." && pwd)")
fi

PATTERNS=(
  'http://localhost'
  'http://127\.0\.0\.1'
  '\.lovable\.(app|dev)'
)

EXCLUDES=(
  '--glob=!**/node_modules/**'
  '--glob=!**/vendor/**'
  '--glob=!**/dist/**'
  '--glob=!**/build/**'
  '--glob=!**/.git/**'
  '--glob=!**/_reference/**'
  '--glob=!**/CHANGELOG.md'
  '--glob=!**/scripts/check-no-internal-urls.sh'
)

fail=0
for ROOT in "${ROOTS[@]}"; do
  for pat in "${PATTERNS[@]}"; do
    if rg -n --no-heading "${EXCLUDES[@]}" "$pat" "$ROOT" 2>/dev/null; then
      echo ""
      echo "ERROR: forbidden URL pattern '$pat' found in $ROOT." >&2
      fail=1
    fi
  done

  # Catch any non-canonical *.supabase.co project ref (allow only the canonical one).
  leaks="$(rg -n --no-heading "${EXCLUDES[@]}" 'https?://[a-z0-9-]+\.supabase\.co' "$ROOT" 2>/dev/null \
      | grep -v 'daslrxpkbkqrbnjwouiq\.supabase\.co' || true)"
  if [[ -n "$leaks" ]]; then
    echo "$leaks" >&2
    echo "" >&2
    echo "ERROR: non-canonical Supabase project URL found in $ROOT. Only daslrxpkbkqrbnjwouiq.supabase.co is allowed." >&2
    fail=1
  fi
done

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo "OK: no leaked URLs in: ${ROOTS[*]}"
