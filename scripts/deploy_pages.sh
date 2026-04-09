#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE_DIR="$ROOT/site"
PROJECT_NAME="rf-marketing-dashboard"
REPO_NAME="marketing-workflow-dashboard"

if [[ ! -f "$SITE_DIR/index.html" ]]; then
  echo "[ERROR] site/index.html not found: $SITE_DIR" >&2
  exit 1
fi

TOKEN="${CLOUDFLARE_API_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  TOKEN="$(security find-generic-password -s "openclaw_cf_admin_token" -w 2>/dev/null || true)"
fi
if [[ -z "$TOKEN" ]]; then
  echo "[ERROR] CLOUDFLARE_API_TOKEN not set and keychain token not found" >&2
  exit 1
fi
export CLOUDFLARE_API_TOKEN="$TOKEN"

printf '\n[deploy] repo=%s\n[deploy] project=%s\n[deploy] site=%s\n\n' "$REPO_NAME" "$PROJECT_NAME" "$SITE_DIR"

grep -q "repo: $REPO_NAME" "$SITE_DIR/index.html" || {
  echo "[ERROR] index.html missing repo badge guard: repo: $REPO_NAME" >&2
  exit 1
}

grep -q "pages: $PROJECT_NAME" "$SITE_DIR/index.html" || {
  echo "[ERROR] index.html missing pages badge guard: pages: $PROJECT_NAME" >&2
  exit 1
}

cd "$SITE_DIR"
npx wrangler pages deploy . --project-name "$PROJECT_NAME" --branch main

echo "\n[ok] deploy finished: $PROJECT_NAME"
