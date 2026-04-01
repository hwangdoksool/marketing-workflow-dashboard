# 8주 회고 데이터 소스 카탈로그

## 기간: 2026-02-03 ~ 2026-03-30 (W6~W13)

## 1. GA4 데이터
- **Full daily**: `~/.openclaw/workspace-ex-asst/marketing-pipeline/data/ga4_full.json`
  - 840일치 daily (20231212~20260331)
  - Keys: date, sessions, users, new_users, bounce_rate, avg_duration, pageviews, engaged_sessions
  - channels: date, channel, sessions, users, bounce_rate (4556 entries)
  - devices, pages
- **Weekly files**: ga4_w9~w13.json (W9=02/23~03/01, W10=03/02~08, W11=03/09~15, W12=03/16~22, W13=03/23~29)
  - Keys: overview, traffic_sources

## 2. Meta Ads 데이터
- **Full daily**: `meta_full.json`
  - 304일 daily (20241030~20260331)
  - Keys: date, impressions, clicks, spend, ctr, cpc, purchases
  - campaigns array
- **Weekly files**: meta_w9~w13.json (same periods)
  - Keys: account_daily, campaigns

## 3. 네이버 검색광고
- **Full**: `naver_full.json`
  - stats: 216 entries (daily from 2024-01-01)
  - Each entry: summary.dateStart/End + data array with ctr, clkCnt, cpc, ccnt, impCnt, salesAmt
- **Weekly files**: naver_w9~w13.json

## 4. Instagram
- **Weekly files**: instagram_2026-02-10~*.json, instagram_2026-03-*.json
- **ig_insights.json**, **ig_follower_history.json**

## 5. YouTube
- **Weekly files**: youtube_2026-02-10~*.json
- **yt_subscriber_history.json**
- **youtube_full.json**

## 6. Blog
- **Weekly files**: blog_2026-02-10~*.json

## 7. 아임웹 매출 (교차검증용)
- 기존 리포트에서 추출 가능:
  - W10: ₩388만 (본체 1대)
  - W11: ₩771만 (본체 2대)
  - W12: ₩796만 (본체 2대)
  - W13: ₩1,079만 (본체 3대+액세서리 1건)
- ⚠️ 아임웹 API 사용 금지 — 브라우저 or 기존 데이터만

## 8. 기존 주간 리포트 (reports.json)
- W10~W13 이미 존재 (KPI, 캠페인별 분석 포함)
- alltime-journey-2026q1 (누적 전체 분석)

## 9. 크리에이티브 데이터
- tagged_creatives_v6.json, meta_ads_creatives.json, naver_ads_creatives.json
- instagram_creatives.json, youtube_creatives.json, blog_creatives.json

## 누락 기간
- W6 (02/03~02/09): 별도 수집 파일 없음 → ga4_full.json daily에서 추출
- W7 (02/10~02/16): 범위 파일 존재 (2026-02-10_2026-02-17)
- W8 (02/17~02/23): 범위 파일 존재 (2026-02-16_2026-02-23, 겹침)
- W9~W13: weekly files 존재

## 교차검증 포인트
1. GA4 purchase events vs 아임웹 실매출 (건수/금액)
2. Meta clicks vs GA4 meta/paid social sessions
3. 네이버 SA clicks vs GA4 naver sessions
4. GA4 revenue vs 아임웹 revenue
5. Instagram reach/engagement vs GA4 social sessions
