#!/bin/bash
# 캠페인 비교 탭 매시 갱신 (launchd: com.openclaw.campaign-compare-hourly, 매시 05분)
# build_campaign_compare.py가 json 갱신 → scripts/deploy_pages.sh 배포까지 한다.
# 실패 시 기존 json 유지, 로그: /tmp/campaign-compare-hourly.log · /tmp/campaign-compare-hourly-err.log
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd /Users/hsw/.openclaw/workspace-ex-asst/marketing-workflow-dashboard || exit 1
/usr/local/bin/python3 scripts/build_campaign_compare.py 2>&1 | grep -v -E "NotOpenSSLWarning|warnings.warn"
status=${PIPESTATUS[0]}
echo "[$(date '+%Y-%m-%d %H:%M:%S')] exit=$status"
exit $status
