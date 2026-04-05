#!/bin/bash
# Weekly report generation wrapper (launchd)
# Runs every Monday 10:00 — generates previous week's report + deploys

set -euo pipefail
cd /Users/hsw/.openclaw/workspace-ex-asst/marketing-workflow-dashboard

echo "$(date): Starting weekly report generation..."

# Generate reports (updates reports.json + weekly_metrics.json)
/opt/homebrew/bin/python3 scripts/generate_reports.py 2>&1

# Deploy to CF Pages
export CLOUDFLARE_API_TOKEN=$(security find-generic-password -s "openclaw_cf_admin_token" -w)
npx wrangler pages deploy site --project-name rf-marketing-dashboard --commit-dirty=true 2>&1

# Git commit
git add site/reports.json site/weekly_metrics.json
git commit -m "chore: auto-generate weekly report $(date +%Y-%m-%d)" 2>/dev/null || true
git push origin main 2>/dev/null || true

echo "$(date): Weekly report generation complete."
